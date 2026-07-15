"""Captura automática de frames para fine-tuning — sem apertar nada.

Salva um frame a cada 1,5s durante 2 minutos (por padrão) enquanto você
movimenta o leque na frente da câmera: perto, longe, inclinado, leque mais
aberto/fechado, cartas diferentes. q encerra antes.

Uso: python training/capture_auto.py [segundos]
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

DURACAO = int(sys.argv[1]) if len(sys.argv) > 1 else 120
INTERVALO = 1.5

OUT = Path(__file__).resolve().parent / "datasets" / "meu-setup"
OUT.mkdir(parents=True, exist_ok=True)

cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)
print(f"capturando 1 frame a cada {INTERVALO}s por {DURACAO}s — "
      "mexa o leque (ângulos, distâncias, cartas). q encerra.")

inicio = time.time()
ultima = 0.0
count = 0
while time.time() - inicio < DURACAO:
    frame = cam.read()
    if frame is not None:
        cv2.imshow("captura (q sai)", frame)
        if time.time() - ultima >= INTERVALO:
            ultima = time.time()
            count += 1
            cv2.imwrite(str(OUT / f"hand_{int(ultima * 1000)}.jpg"), frame)
            print(f"frame {count}")
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break

cam.stop()
cv2.destroyAllWindows()
print(f"{count} frames em {OUT}")
