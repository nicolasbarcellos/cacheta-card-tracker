"""Mostra cada índice de câmera, para achar QUAL deles é a webcam da mão.

O Windows renumera os índices ao reconectar o USB, e o sintoma é o preview
da mão mostrando outra coisa. Aqui aparecem todos os índices que abrirem.
"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

cams = {f"indice {i}": CameraStream(i, config.frame_width, config.frame_height)
        for i in range(3)}
print(f"q para sair. hand_cam_index atual = {config.hand_cam_index} "
      f"(ajustar em app/config.py se não for a da mão)")
while True:
    for name, cam in cams.items():
        frame = cam.read()
        if frame is not None:
            cv2.imshow(name, frame)
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break
for cam in cams.values():
    cam.stop()
cv2.destroyAllWindows()
