"""Captura frames das 2 webcams para montar o dataset de fine-tuning.

Espaço = salva frame das duas câmeras; q = sair.
Capturar ~100-200 frames variados por câmera: cartas diferentes, leque
aberto/fechado, mão em ângulos diferentes, com e sem oclusão parcial.
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

OUT = Path(__file__).resolve().parent / "datasets" / "meu-setup"
OUT.mkdir(parents=True, exist_ok=True)

cams = {
    "discard": CameraStream(config.discard_cam_index,
                            config.frame_width, config.frame_height),
    "hand": CameraStream(config.hand_cam_index,
                         config.frame_width, config.frame_height),
}
count = 0
print("espaço = capturar, q = sair")
while True:
    frames = {}
    for name, cam in cams.items():
        frame = cam.read()
        if frame is not None:
            frames[name] = frame
            cv2.imshow(name, frame)
    key = cv2.waitKey(30) & 0xFF
    if key == ord(" "):
        stamp = int(time.time() * 1000)
        for name, frame in frames.items():
            path = OUT / f"{name}_{stamp}.jpg"
            cv2.imwrite(str(path), frame)
        count += 1
        print(f"captura {count}")
    elif key == ord("q"):
        break
for cam in cams.values():
    cam.stop()
cv2.destroyAllWindows()
print(f"{count} capturas em {OUT}")
