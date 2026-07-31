"""Captura frames REAIS com rótulo vindo da ORDEM, não do modelo.

O ciclo normal (capture_auto + auto_annotate) rotula com o modelo atual e
depende de revisão manual. Isso tem um limite fatal para as cartas que o
modelo erra: os frames dessas cartas saem com rótulo errado, são apagados na
revisão, e a carta nunca aprende. É exatamente o caso da confusão A↔4.

Aqui o rótulo vem de fora: você informa a mão na ORDEM da esquerda para a
direita, e cada detecção recebe o código da sua posição — o que o modelo
"achou" é ignorado. Assim se produz dado correto justamente onde ele erra.

Guardas contra alinhamento torto (uma carta não detectada desloca todos os
rótulos seguintes e envenenaria o dataset):
  - o frame precisa ter EXATAMENTE tantas detecções quanto cartas informadas;
  - o espaçamento entre cantos vizinhos não pode ter buraco (sinal de carta
    faltando no meio);
  - a maioria dos rótulos do modelo já tem de bater com a posição — se quase
    nada bate, o alinhamento provavelmente está deslocado e o frame é pulado.

Uso:
  python training/capture_rotulado.py "AS 4S AH 4H AD 4D AC 4C KS" [segundos]
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.cards import Card  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, hand_instances  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)

MAO = [Card.from_label(c).code for c in sys.argv[1].split()]
DURACAO = int(sys.argv[2]) if len(sys.argv) > 2 else 60
INTERVALO = 0.4          # evita salvar frames quase idênticos
MIN_CONCORDA = 0.5       # fração dos rótulos do modelo que deve bater
GAP_MAX = 2.2            # buraco no espaçamento = carta faltando

ROOT = Path(__file__).resolve().parent
DST = ROOT / "datasets" / "local"
for sub in ("images", "labels", "review"):
    (DST / sub).mkdir(parents=True, exist_ok=True)


def alinhamento_confiavel(dets):
    """As detecções formam uma fileira sem buraco, na contagem esperada?"""
    if len(dets) != len(MAO):
        return False, "contagem"
    xs = [(d.box[0] + d.box[2]) / 2 for d in dets]
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    if gaps:
        meio = sorted(gaps)[len(gaps) // 2]
        if meio > 0 and max(gaps) > GAP_MAX * meio:
            return False, "buraco no leque"
    concorda = sum(1 for d, code in zip(dets, MAO) if d.card.code == code)
    if concorda < MIN_CONCORDA * len(MAO):
        return False, f"so {concorda}/{len(MAO)} batem"
    return True, f"{concorda}/{len(MAO)} batem"


det = CardDetector(config.model_path, config.min_confidence,
                   imgsz=config.detect_imgsz,
                   agnostic_nms=config.agnostic_nms)
name_to_id = {name: i for i, name in det.model.names.items()}
cam = CameraStream(config.hand_cam_index, config.frame_width,
                   config.frame_height)

print(f"mão informada ({len(MAO)} cartas): {' '.join(MAO)}")
print(f"capturando {DURACAO}s — varie distância, ângulo e abertura", flush=True)

salvos = 0
pulados: dict = {}
ultimo = 0.0
t0 = time.time()
while time.time() - t0 < DURACAO:
    frame = cam.read()
    if frame is None or time.time() - ultimo < INTERVALO:
        time.sleep(0.02)
        continue
    dets = sorted(hand_instances(det.detect(frame)),
                  key=lambda d: (d.box[0] + d.box[2]) / 2)
    ok, motivo = alinhamento_confiavel(dets)
    if not ok:
        pulados[motivo] = pulados.get(motivo, 0) + 1
        continue

    ultimo = time.time()
    h, w = frame.shape[:2]
    linhas, view = [], frame.copy()
    for d, code in zip(dets, MAO):
        x1, y1, x2, y2 = d.box
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        bw, bh = (x2 - x1) / w, (y2 - y1) / h
        linhas.append(f"{name_to_id[code]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        cor = (0, 255, 0) if d.card.code == code else (0, 165, 255)
        cv2.rectangle(view, (x1, y1), (x2, y2), cor, 2)
        cv2.putText(view, code, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, cor, 2)

    nome = f"ord_{int(time.time() * 1000)}"
    cv2.imwrite(str(DST / "images" / f"{nome}.jpg"), frame)
    (DST / "labels" / f"{nome}.txt").write_text("\n".join(linhas))
    cv2.imwrite(str(DST / "review" / f"{nome}.jpg"), view)
    salvos += 1
    if salvos % 10 == 0:
        print(f"  {salvos} frames ({motivo})", flush=True)

cam.stop()
print(f"\n{salvos} frames salvos em {DST}")
if pulados:
    print("pulados:")
    for motivo, n in sorted(pulados.items(), key=lambda kv: -kv[1]):
        print(f"  {motivo}: {n}")
print("\nlaranja no review = carta que o modelo errou e foi CORRIGIDA pela ordem")
