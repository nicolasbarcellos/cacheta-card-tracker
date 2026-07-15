"""Mostra as duas webcams lado a lado para conferir índices/foco/enquadramento."""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

cams = {
    "descarte": CameraStream(config.discard_cam_index,
                             config.frame_width, config.frame_height),
    "mao": CameraStream(config.hand_cam_index,
                        config.frame_width, config.frame_height),
}
print("q para sair. Se as câmeras estiverem trocadas, ajustar índices em app/config.py")
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
