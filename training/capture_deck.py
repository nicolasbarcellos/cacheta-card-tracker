"""Captura o molde de cada carta do baralho — MODO SEQUÊNCIA (sem modelo).

O programa DIZ qual carta colocar ("PROXIMA: AS"). Você deita a carta na
mesa escura dentro da moldura, tira a mão e aperta ESPAÇO. O recorte é
geométrico (nenhum modelo envolvido — funciona com qualquer baralho).

Teclas:
  ESPAÇO  captura a carta anunciada
  p       pula a anunciada para o fim da fila
  t       digitar outra carta (valor: a 2-9 0=10 j q k; naipe: s h d c)
  q       encerra e lista as que faltam

Ordem anunciada: A♠ A♥ A♦ A♣, 2♠ 2♥ 2♦ 2♣, ... K♣ (deixe o baralho
organizado assim que vira uma tecla por carta).
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.cards import RANKS, SUITS  # noqa: E402
from app.config import config  # noqa: E402

TEMPLATE_W, TEMPLATE_H = 250, 350
OUT = Path(__file__).resolve().parent / "templates"
OUT.mkdir(parents=True, exist_ok=True)

ORDER = [f"{r}{s}" for r in RANKS for s in SUITS]
NICE = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

RANK_KEYS = {ord("a"): "A", ord("2"): "2", ord("3"): "3", ord("4"): "4",
             ord("5"): "5", ord("6"): "6", ord("7"): "7", ord("8"): "8",
             ord("9"): "9", ord("0"): "10", ord("j"): "J", ord("q"): "Q",
             ord("k"): "K"}
SUIT_KEYS = {ord("s"): "S", ord("h"): "H", ord("d"): "D", ord("c"): "C"}


def guide_rect(frame):
    h, w = frame.shape[:2]
    gh = int(h * 0.62)
    gw = int(gh * 70 / 88)
    x1 = (w - gw) // 2
    y1 = int(h * 0.30)
    return x1, y1, x1 + gw, min(y1 + gh, h - 4)


def extract_card(crop, corner_pt):
    """Recorta o retângulo exato da carta (bloco claro contendo o ponto
    semente, com proporção de carta). Retorna (molde, None) ou (None, motivo)."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    _, sat, val = cv2.split(hsv)
    mask = ((sat < 70) & (val > 110)).astype(np.uint8) * 255
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    area_crop = crop.shape[0] * crop.shape[1]
    rect = None
    for c in contours:
        area = cv2.contourArea(c)
        if not area_crop * 0.18 <= area <= area_crop * 0.80:
            if area > area_crop * 0.80 and cv2.pointPolygonTest(
                    c, corner_pt, False) >= 0:
                return None, "fundo claro na moldura"
            continue
        if cv2.pointPolygonTest(c, corner_pt, False) < 0:
            continue
        r = cv2.minAreaRect(c)
        (w, h) = r[1]
        if w == 0 or h == 0:
            continue
        ratio = min(w, h) / max(w, h)
        if 0.60 <= ratio <= 0.84:  # carta é ~63/88 = 0.72
            rect = r
            break
    if rect is None:
        return None, "carta nao isolada (mao no quadro?)"
    box = cv2.boxPoints(rect).astype(np.float32)
    s = box.sum(axis=1)
    d = np.diff(box, axis=1).ravel()
    ordered = np.array([box[np.argmin(s)], box[np.argmin(d)],
                        box[np.argmax(s)], box[np.argmax(d)]], np.float32)
    top_w = float(np.linalg.norm(ordered[1] - ordered[0]))
    left_h = float(np.linalg.norm(ordered[3] - ordered[0]))
    dst_w, dst_h = ((TEMPLATE_W, TEMPLATE_H) if top_w <= left_h
                    else (TEMPLATE_H, TEMPLATE_W))
    dst = np.array([[0, 0], [dst_w - 1, 0], [dst_w - 1, dst_h - 1],
                    [0, dst_h - 1]], np.float32)
    m = cv2.getPerspectiveTransform(ordered, dst)
    card = cv2.warpPerspective(crop, m, (dst_w, dst_h))
    if dst_w != TEMPLATE_W:
        card = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE)
    return card, None


def sharpness(crop):
    return cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY),
                         cv2.CV_64F).var()


def typed_code(base_view):
    """t: usuário digita valor+naipe. Retorna code ou None (ESC)."""
    parts = []
    while True:
        view = base_view.copy()
        txt = ("valor? a 2-9 0(=10) j q k" if not parts
               else f"{parts[0]} + naipe? s h d c   (ESC cancela)")
        cv2.putText(view, txt, (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (0, 200, 255), 3)
        cv2.imshow("captura do baralho (q sai)", view)
        key = cv2.waitKey(50) & 0xFF
        if key == 27:
            return None
        if not parts and key in RANK_KEYS:
            parts.append(RANK_KEYS[key])
        elif parts and key in SUIT_KEYS:
            return parts[0] + SUIT_KEYS[key]


def main():
    cam = CameraStream(config.hand_cam_index, config.frame_width,
                       config.frame_height)
    have = {p.stem for p in OUT.glob("*.png")}
    queue = [c for c in ORDER if c not in have]
    flash_until, flash_text, flash_ok = 0.0, "", True
    last_dump = 0.0
    print(f"{len(have)}/52 salvas; fila: {len(queue)}", flush=True)

    while True:
        frame = cam.read()
        if frame is None:
            if cv2.waitKey(100) & 0xFF == ord("q"):
                break
            continue
        x1, y1, x2, y2 = guide_rect(frame)
        proxima = queue[0] if queue else None

        view = frame.copy()
        color = (0, 255, 0) if time.time() < flash_until and flash_ok else \
                (0, 0, 255) if time.time() < flash_until else (0, 200, 255)
        cv2.rectangle(view, (x1, y1), (x2, y2), color, 4)
        if proxima:
            nice = proxima[:-1] + NICE[proxima[-1]]
            cv2.putText(view, f"PROXIMA: {nice} ({proxima})", (x1 - 40, y1 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 200, 255), 4)
        else:
            cv2.putText(view, "BARALHO COMPLETO! (q sai)", (x1 - 60, y1 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 255, 0), 3)
        if time.time() < flash_until:
            cv2.putText(view, flash_text, (x1 - 60, y2 + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
        cv2.putText(view, f"{52 - len(queue)}/52", (30, view.shape[0] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 255), 3)
        cv2.putText(view, "ESPACO captura | p pula | t digitar | q sai",
                    (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        if time.time() - last_dump > 2:
            last_dump = time.time()
            cv2.imwrite(str(OUT.parent / "live_view.jpg"), view)
        cv2.imshow("captura do baralho (q sai)", view)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("p") and queue:
            queue.append(queue.pop(0))
        elif key in (ord(" "), ord("t")):
            crop = frame[y1:y2, x1:x2]
            if sharpness(crop) < 80:
                flash_until, flash_text, flash_ok = (time.time() + 1.2,
                                                     "X borrada, de novo",
                                                     False)
                continue
            code = proxima if key == ord(" ") else typed_code(view)
            if not code:
                continue
            center = ((x2 - x1) / 2, (y2 - y1) / 2)
            card_img, reason = extract_card(crop, center)
            if card_img is None:
                flash_until, flash_text, flash_ok = (time.time() + 1.5,
                                                     f"X {reason}", False)
                print(f"{code}: {reason}", flush=True)
                continue
            cv2.imwrite(str(OUT / f"{code}.png"), card_img)
            if code in queue:
                queue.remove(code)
            print(f"capturada: {code} ({52 - len(queue)}/52)", flush=True)
            flash_until, flash_text, flash_ok = (time.time() + 0.8,
                                                 f"CAPTURADA: {code}", True)

    cam.stop()
    cv2.destroyAllWindows()
    print(f"\n{52 - len(queue)}/52 moldes em {OUT}", flush=True)
    if queue:
        print("faltam: " + ", ".join(queue), flush=True)
    else:
        print("baralho completo!", flush=True)


if __name__ == "__main__":
    main()
