"""Gera leques sintéticos a partir dos moldes do baralho, com gabarito exato.

Monta cenas de leque (2 a 10 cartas, maioria 9) colando os moldes de
training/templates/ com rotação/sobreposição/iluminação variadas sobre
fundos aleatórios (ou fotos de training/backgrounds/, se existirem).
Como a geometria é conhecida, os cantos visíveis viram labels YOLO exatos.

Uso: python training/generate_fans.py [n_imagens]   (padrão: 1500)
Saída: training/datasets/synthetic/{images,labels}/
"""
import random
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cards import RANKS, SUITS  # noqa: E402

N_IMAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
CANVAS_W, CANVAS_H = 1280, 720
TPL_W, TPL_H = 250, 350
# região do índice (valor+naipe) no molde 250x350 — ~8x18mm de uma carta 63x88
CORNER_TL = np.array([[8, 10], [48, 10], [48, 85], [8, 85]], np.float32)
CORNER_BR = np.array([[TPL_W - 48, TPL_H - 85], [TPL_W - 8, TPL_H - 85],
                      [TPL_W - 8, TPL_H - 10], [TPL_W - 48, TPL_H - 10]],
                     np.float32)

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
BACKGROUNDS = ROOT / "backgrounds"
OUT = ROOT / "datasets" / "synthetic"
(OUT / "images").mkdir(parents=True, exist_ok=True)
(OUT / "labels").mkdir(parents=True, exist_ok=True)

ALL_CODES = sorted(f"{r}{s}" for r in RANKS for s in SUITS)
NAME_TO_ID = {c: i for i, c in enumerate(ALL_CODES)}  # mesma ordem do modelo


def load_templates():
    templates = {}
    for p in TEMPLATES.glob("*.png"):
        img = cv2.imread(str(p))
        if img is not None and p.stem in NAME_TO_ID:
            templates[p.stem] = cv2.resize(img, (TPL_W, TPL_H))
    return templates


def random_background():
    files = list(BACKGROUNDS.glob("*.jpg")) + list(BACKGROUNDS.glob("*.png"))
    if files and random.random() < 0.8:
        img = cv2.imread(str(random.choice(files)))
        if img is not None:
            return cv2.resize(img, (CANVAS_W, CANVAS_H))
    # fundo procedural: cor sólida escura com gradiente e ruído
    base = np.full((CANVAS_H, CANVAS_W, 3),
                   [random.randint(15, 90) for _ in range(3)], np.uint8)
    grad = np.linspace(random.uniform(0.7, 1.0), random.uniform(1.0, 1.3),
                       CANVAS_H, dtype=np.float32).reshape(-1, 1, 1)
    noisy = np.clip(base * grad + np.random.normal(0, 6, base.shape), 0, 255)
    return noisy.astype(np.uint8)


def jitter_card(img):
    img = img.astype(np.float32)
    img *= random.uniform(0.6, 1.25)               # brilho
    img += np.random.uniform(-12, 12, 3)           # tom de cor
    return np.clip(img, 0, 255).astype(np.uint8)


def affine_for(scale, angle_deg, pivot, base_center):
    """Molde em pé centrado em base_center, girado angle_deg em torno de pivot."""
    place = np.array([[scale, 0, base_center[0] - TPL_W * scale / 2],
                      [0, scale, base_center[1] - TPL_H * scale / 2],
                      [0, 0, 1]], np.float32)
    rot = np.vstack([cv2.getRotationMatrix2D(pivot, angle_deg, 1.0),
                     [0, 0, 1]]).astype(np.float32)
    return (rot @ place)[:2]


def compose_fan(templates):
    canvas = random_background()
    n = random.choice([2, 5, 7, 8] + [9] * 8 + [10] * 2)
    codes = random.sample(list(templates), min(n, len(templates)))
    scale = random.uniform(0.55, 1.15)
    spread = random.uniform(3.5, 8.0) * (len(codes) - 1)  # graus por carta
    cx = random.uniform(CANVAS_W * 0.25, CANVAS_W * 0.75)
    cy = random.uniform(CANVAS_H * 0.35, CANVAS_H * 0.75)
    pivot = (cx, cy + TPL_H * scale * random.uniform(0.9, 1.6))

    polys, corners = [], []
    for i, code in enumerate(codes):
        angle = -spread / 2 + spread * (i / max(len(codes) - 1, 1))
        angle += random.uniform(-1.5, 1.5)
        m = affine_for(scale, -angle, pivot, (cx, cy))
        card = jitter_card(templates[code])
        warped = cv2.warpAffine(card, m, (CANVAS_W, CANVAS_H))
        mask = cv2.warpAffine(np.full((TPL_H, TPL_W), 255, np.uint8), m,
                              (CANVAS_W, CANVAS_H))
        canvas[mask > 127] = warped[mask > 127]

        quad = cv2.transform(np.array([[[0, 0], [TPL_W, 0], [TPL_W, TPL_H],
                                        [0, TPL_H]]], np.float32), m)[0]
        polys.append(quad)
        for corner in (CORNER_TL, CORNER_BR):
            pts = cv2.transform(corner.reshape(1, -1, 2), m)[0]
            corners.append((i, code, pts))

    labels = []
    for owner, code, pts in corners:
        center = tuple(pts.mean(axis=0))
        covered = any(cv2.pointPolygonTest(polys[j].astype(np.float32),
                                           center, False) >= 0
                      for j in range(owner + 1, len(polys)))
        x1, y1 = pts.min(axis=0)
        x2, y2 = pts.max(axis=0)
        inside = 0 <= x1 and 0 <= y1 and x2 < CANVAS_W and y2 < CANVAS_H
        if covered or not inside:
            continue
        labels.append(f"{NAME_TO_ID[code]} "
                      f"{(x1 + x2) / 2 / CANVAS_W:.6f} "
                      f"{(y1 + y2) / 2 / CANVAS_H:.6f} "
                      f"{(x2 - x1) / CANVAS_W:.6f} "
                      f"{(y2 - y1) / CANVAS_H:.6f}")

    if random.random() < 0.3:
        canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
    return canvas, labels


def main():
    templates = load_templates()
    if len(templates) < 40:
        sys.exit(f"só {len(templates)} moldes em {TEMPLATES} — "
                 "rode capture_deck.py até fechar as 52 cartas")
    print(f"{len(templates)} moldes; gerando {N_IMAGES} leques...")
    for i in range(N_IMAGES):
        canvas, labels = compose_fan(templates)
        if not labels:
            continue
        cv2.imwrite(str(OUT / "images" / f"fan_{i:05d}.jpg"), canvas,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        (OUT / "labels" / f"fan_{i:05d}.txt").write_text("\n".join(labels))
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{N_IMAGES}")
    print(f"pronto: {OUT}")


if __name__ == "__main__":
    main()
