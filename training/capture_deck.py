"""Captura o molde de cada carta do baralho, uma por vez.

Mostre UMA carta de cada vez, de frente, preenchendo boa parte do quadro,
sobre fundo contrastante (ex.: mesa escura). O script recorta a carta,
identifica qual é e salva o molde em training/templates/{codigo}.png.

Na janela: verde = carta capturada; contador mostra o progresso (n/52).
Pode passar o baralho na ordem que quiser; repetida substitui se a nova
leitura for mais confiante. q encerra e lista as que faltam.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.cards import RANKS, SUITS  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector  # noqa: E402

TEMPLATE_W, TEMPLATE_H = 250, 350
OUT = Path(__file__).resolve().parent / "templates"
OUT.mkdir(parents=True, exist_ok=True)

ALL_CODES = {f"{r}{s}" for r in RANKS for s in SUITS}


def find_card_quad(frame):
    """Maior contorno de 4 pontos ocupando boa parte do quadro."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    frame_area = frame.shape[0] * frame.shape[1]
    best = None
    for c in contours:
        area = cv2.contourArea(c)
        if area < frame_area * 0.08:
            continue
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and (best is None or area > best[1]):
            best = (approx.reshape(4, 2).astype(np.float32), area)
    return None if best is None else best[0]


def warp_card(frame, quad):
    """Retifica o quadrilátero para o molde em pé (250x350)."""
    s = quad.sum(axis=1)
    d = np.diff(quad, axis=1).ravel()
    ordered = np.array([quad[np.argmin(s)], quad[np.argmin(d)],
                        quad[np.argmax(s)], quad[np.argmax(d)]],
                       dtype=np.float32)  # tl, tr, br, bl
    dst = np.array([[0, 0], [TEMPLATE_W - 1, 0],
                    [TEMPLATE_W - 1, TEMPLATE_H - 1], [0, TEMPLATE_H - 1]],
                   dtype=np.float32)
    m = cv2.getPerspectiveTransform(ordered, dst)
    return cv2.warpPerspective(frame, m, (TEMPLATE_W, TEMPLATE_H))


def main():
    detector = CardDetector(config.model_path, min_confidence=0.5)
    cam = CameraStream(config.hand_cam_index, config.frame_width,
                       config.frame_height)
    best_conf: dict[str, float] = {}
    for existing in OUT.glob("*.png"):  # retomar sessão anterior
        best_conf.setdefault(existing.stem, 0.51)

    print("mostre UMA carta por vez; q encerra")
    while True:
        frame = cam.read()
        if frame is None:
            if cv2.waitKey(100) & 0xFF == ord("q"):
                break
            continue
        view = frame.copy()
        quad = find_card_quad(frame)
        if quad is not None:
            card_img = warp_card(frame, quad)
            # identifica pela leitura dos cantos no molde ampliado
            big = cv2.resize(card_img, (TEMPLATE_W * 2, TEMPLATE_H * 2))
            dets = detector.detect(big)
            if dets:
                top = max(dets, key=lambda dd: dd.confidence)
                code, conf = top.card.code, top.confidence
                if conf > best_conf.get(code, 0.0):
                    best_conf[code] = conf
                    cv2.imwrite(str(OUT / f"{code}.png"), card_img)
                cv2.polylines(view, [quad.astype(int)], True, (0, 255, 0), 3)
                cv2.putText(view, f"{code} {conf:.2f}", (30, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 0), 3)
        captured = len(best_conf)
        cv2.putText(view, f"{captured}/52", (30, view.shape[0] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 255), 3)
        cv2.imshow("captura do baralho (q sai)", view)
        if cv2.waitKey(30) & 0xFF == ord("q"):
            break

    cam.stop()
    cv2.destroyAllWindows()
    missing = sorted(ALL_CODES - set(best_conf))
    print(f"\n{len(best_conf)}/52 moldes em {OUT}")
    if missing:
        print("faltam: " + ", ".join(missing))
    else:
        print("baralho completo!")


if __name__ == "__main__":
    main()
