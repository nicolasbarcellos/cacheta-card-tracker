"""Diagnóstico AO VIVO: janela para enquadrar + log por frame.

Enquadre o leque na janela (vê as caixas em tempo real) e segure parado.
A cada ~0.4s imprime quantas cartas o modelo detectou e quais/confiança.
q encerra. Também salva o melhor frame anotado (mais detecções).
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, draw_boxes  # noqa: E402

OUT = Path(__file__).resolve().parent
cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)
det = CardDetector(config.model_path, min_confidence=0.25,
                   imgsz=config.detect_imgsz)
for _ in range(60):
    time.sleep(0.3)
    if cam.read() is not None:
        break

print("enquadre o leque na janela e segure; q encerra", flush=True)
best_n, last_log = 0, 0.0
t0 = time.time()
while time.time() - t0 < 40:
    f = cam.read()
    if f is None:
        if cv2.waitKey(50) & 0xFF == ord("q"):
            break
        continue
    dets = det.detect(f)
    view = draw_boxes(f, dets)
    cv2.putText(view, f"{len(dets)} cartas", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 255), 3)
    cv2.imshow("diagnostico (q sai)", view)
    if time.time() - last_log > 0.4:
        last_log = time.time()
        codes = sorted(f"{d.card.code}:{d.confidence:.2f}" for d in dets)
        print(f"{len(dets):2d} -> {codes}", flush=True)
    if len(dets) > best_n:
        best_n = len(dets)
        cv2.imwrite(str(OUT / "diag_best.jpg"), view)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cam.stop()
cv2.destroyAllWindows()
print(f"\nmelhor frame: {best_n} cartas (diag_best.jpg)", flush=True)
