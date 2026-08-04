"""Mostra a ordem em que o leitor vê o leque, para conferir ANTES de capturar.

Existe por causa de um envenenamento real: em 2026-08-04 uma captura de 63
frames passou por todas as guardas do `capture_rotulado.py` com os quatro oitos
rotulados errados — a mão informada tinha os naipes numa ordem, a mão física em
outra. `MIN_CONCORDA = 0.5` deixou passar porque as outras cinco cartas batiam.
Treinar com aquilo teria ensinado justamente a confusão de naipe que a captura
existia para consertar.

A guarda que faltava não é mais uma heurística: é OLHAR. Este script pega um
frame, numera as detecções da esquerda para a direita — que é a ordem que o
`capture_rotulado.py` espera receber — e salva a imagem para conferência.
Compare o rótulo com a carta na foto antes de gravar 60 segundos.

Imprime também o espaçamento horizontal entre os cantos. Ele importa tanto
quanto a ordem: com o leque abrindo para CIMA em vez de para os lados, cartas
vizinhas saíram a 3 px uma da outra, e a ordenação por x que decide o rótulo
vira sorteio a cada tremor. Uma troca entre vizinhas ainda deixa 7 de 9 batendo
e passa na guarda. Exija dezenas de px.

Uso: python training/ver_ordem.py [saida.jpg]
"""
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, hand_instances  # noqa: E402

SAIDA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ordem.jpg"
ESPERA = 12          # s procurando o melhor frame
GAP_ALERTA = 25      # px: abaixo disso a ordenação por x é frágil

det = CardDetector(config.model_path, config.min_confidence,
                   imgsz=config.detect_imgsz, agnostic_nms=config.agnostic_nms)
cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)

print(f"segure o leque parado — procurando o melhor frame por {ESPERA}s",
      flush=True)
melhor = None
t0 = time.time()
while time.time() - t0 < ESPERA:
    frame = cam.read()
    if frame is None:
        time.sleep(0.05)
        continue
    dets = sorted(hand_instances(det.detect(frame)),
                  key=lambda d: (d.box[0] + d.box[2]) / 2)
    if melhor is None or len(dets) > len(melhor[1]):
        melhor = (frame.copy(), dets)
    if len(dets) >= config.hand_size:
        break
    time.sleep(0.05)
cam.stop()

if melhor is None:
    sys.exit("nenhum frame lido da câmera")

frame, dets = melhor
for i, d in enumerate(dets):
    x1, y1, x2, y2 = d.box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(frame, f"{i + 1}:{d.card.code}", (x1 - 4, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
cv2.imwrite(str(SAIDA), frame)

codigos = [d.card.code for d in dets]
xs = [int((d.box[0] + d.box[2]) / 2) for d in dets]
gaps = [b - a for a, b in zip(xs, xs[1:])]

print(f"\n{len(dets)} detecções, da esquerda para a direita:")
print("  " + " ".join(codigos))
print("  conf:  " + " ".join(f"{d.confidence:.2f}" for d in dets))
print("  x:     " + " ".join(str(x) for x in xs))
if gaps:
    print("  gaps:  " + " ".join(str(g) for g in gaps))
    if min(gaps) < GAP_ALERTA:
        print(f"\n  !! menor gap = {min(gaps)} px (< {GAP_ALERTA}): abra o leque "
              f"mais para os LADOS antes de capturar — nessa distância a ordem "
              f"pode trocar entre frames e os rótulos trocam junto")
if len(dets) != config.hand_size:
    print(f"\n  !! {len(dets)} detecções para uma mão de {config.hand_size}: "
          f"o capture_rotulado vai descartar esses frames por contagem")
print(f"\nCONFIRA A IMAGEM antes de capturar: {SAIDA}")
print(f'depois: python training/capture_rotulado.py "{" ".join(codigos)}" 60')
