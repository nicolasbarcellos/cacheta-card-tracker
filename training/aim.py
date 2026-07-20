"""Só para mirar a câmera: janela ao vivo com alvo central.

Incline/gire a câmera (não as cartas) até sua mão com o leque ficar
DENTRO do retângulo verde central, preenchendo boa parte dele.
Mostra também quantas cartas o modelo vê (ajuda a confirmar). q encerra.
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

print("mire a camera: leque no centro; q encerra", flush=True)
last = 0.0
t0 = time.time()
while time.time() - t0 < 120:
    f = cam.read()
    if f is None:
        if cv2.waitKey(50) & 0xFF == ord("q"):
            break
        continue
    dets = det.detect(f)
    view = draw_boxes(f, dets)
    h, w = view.shape[:2]
    cv2.rectangle(view, (int(w*0.3), int(h*0.2)), (int(w*0.7), int(h*0.85)),
                  (0, 255, 0), 3)
    cv2.putText(view, f"{len(dets)} cartas - leque DENTRO do retangulo",
                (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 200, 255), 3)
    cv2.imshow("MIRAR (q sai)", view)
    if time.time() - last > 1.0:
        last = time.time()
        print(f"{len(dets)} cartas", flush=True)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cam.stop()
cv2.destroyAllWindows()
