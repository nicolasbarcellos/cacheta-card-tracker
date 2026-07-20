"""Mede a estabilidade da detecção frame a frame no leque real.

Captura ~40 frames em ~10s, roda o modelo em cada um em VÁRIAS confianças
e resoluções, e reporta: quantas cartas por frame, quais, e confiança.
Salva 3 frames anotados + os frames crus para inspeção.
"""
import sys
import time
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, draw_boxes  # noqa: E402

OUT = Path(__file__).resolve().parent
cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)
for _ in range(60):
    time.sleep(0.3)
    if cam.read() is not None:
        break

det_hi = CardDetector(config.model_path, min_confidence=0.25,
                      imgsz=config.detect_imgsz)

print(">>> SEGURE O LEQUE PARADO - medindo 10s <<<", flush=True)
frames = []
t0 = time.time()
while time.time() - t0 < 10:
    f = cam.read()
    if f is not None:
        frames.append(f.copy())
    time.sleep(0.25)
cam.stop()

print(f"\n{len(frames)} frames capturados. Análise por frame (conf>=0.25):",
      flush=True)
counts = []
allcards = Counter()
saved = 0
for i, f in enumerate(frames):
    dets = det_hi.detect(f)
    codes = sorted(f"{d.card.code}:{d.confidence:.2f}" for d in dets)
    n = len(dets)
    counts.append(n)
    for d in dets:
        allcards[d.card.code] += 1
    if i % 8 == 0:
        print(f"  frame {i:2d}: {n:2d} cartas -> {codes}", flush=True)
    if saved < 3 and n >= 5:
        cv2.imwrite(str(OUT / f"diag_{saved}.jpg"), draw_boxes(f, dets))
        saved += 1

print(f"\nRESUMO:", flush=True)
print(f"  cartas por frame: min={min(counts)} max={max(counts)} "
      f"media={sum(counts)/len(counts):.1f}", flush=True)
print(f"  frequencia de cada carta (em {len(frames)} frames):", flush=True)
for code, c in allcards.most_common():
    print(f"    {code}: {c}/{len(frames)} frames ({100*c//len(frames)}%)",
          flush=True)
cv2.imwrite(str(OUT / "diag_last.jpg"), frames[-1])
