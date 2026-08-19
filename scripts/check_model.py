"""Mostra a câmera da mão com as detecções do modelo treinado."""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, draw_boxes  # noqa: E402

detector = CardDetector(config.model_path, min_confidence=0.5)
cam = CameraStream(config.hand_cam_index,
                   config.frame_width, config.frame_height)
print("mostre uma carta para a câmera; q para sair")
while True:
    frame = cam.read()
    if frame is not None:
        cv2.imshow("modelo", draw_boxes(frame, detector.detect(frame)))
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break
cam.stop()
cv2.destroyAllWindows()
