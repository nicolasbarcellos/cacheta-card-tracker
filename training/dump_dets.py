"""Captura um frame com o leque e despeja TODAS as detecções com coords.

Espera por um frame com >=8 detecções, salva anotado e imprime cada
detecção (code, conf, centro x/y, largura/altura da caixa) para eu
analisar a geometria do canto de baixo (Ás contado 2x).
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, draw_boxes  # noqa: E402

cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)
det = CardDetector(config.model_path, min_confidence=0.25,
                   imgsz=config.detect_imgsz)
for _ in range(60):
    time.sleep(0.3)
    if cam.read() is not None:
        break

print("procurando frame com o leque (>=8 cartas)...", flush=True)
best = None
t0 = time.time()
while time.time() - t0 < 20:
    f = cam.read()
    if f is None:
        time.sleep(0.2)
        continue
    dets = det.detect(f)
    if best is None or len(dets) > len(best[1]):
        best = (f.copy(), dets)
    if len(dets) >= 9:
        break
    time.sleep(0.2)
cam.stop()

f, dets = best
cv2.imwrite(str(Path(__file__).parent / "dump.jpg"), draw_boxes(f, dets))
print(f"\n{len(dets)} deteccoes:", flush=True)
for d in sorted(dets, key=lambda d: (d.box[0] + d.box[2]) / 2):
    x1, y1, x2, y2 = d.box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    print(f"  {d.card.code:3s} conf={d.confidence:.2f} "
          f"cx={cx:.0f} cy={cy:.0f} w={x2-x1:.0f} h={y2-y1:.0f}", flush=True)
