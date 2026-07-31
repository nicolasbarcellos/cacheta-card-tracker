"""Pseudo-anotação local: o modelo atual anota os frames capturados.

Para cada .jpg em training/datasets/meu-setup/ roda o modelo com confiança
alta e gera:
  - training/datasets/local/images/  (a foto)
  - training/datasets/local/labels/  (anotação YOLO .txt)
  - training/datasets/local/review/  (foto com as caixas desenhadas)

Frames cuja contagem de cartas foge do esperado (ver ESPERADO) são descartados
automaticamente: ou ficou carta sem caixa, ou apareceu fantasma. Isso poupa a
revisão manual de olhar foto por foto só para achar anotação incompleta.

REVISÃO: abra a pasta review/ no Explorer e APAGUE as imagens em que o
modelo errou o RÓTULO (ex.: 4♦ anotado como A♦). O treino (finetune_local.py)
só usa os frames cuja imagem de review sobreviveu.

Uso: python training/auto_annotate.py [confianca]
"""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.detector import (CardDetector, draw_boxes,  # noqa: E402
                          hand_instances)

# Confiança da pseudo-anotação, ajustável na linha de comando.
# 0.45 media 8 rótulos por frame numa mão de 9: descartava carta real, e frame
# com índice VISÍVEL e sem rótulo ensina o modelo que aquele padrão é fundo —
# pior que perder a amostra. Limiar mais baixo cobre mais e erra mais; quem
# limpa o excesso é o filtro por contagem esperada, abaixo.
CONF = float(sys.argv[1]) if len(sys.argv) > 1 else 0.30

# A mão tem um número CONHECIDO de cartas distintas. Frame anotado com outra
# contagem está incompleto (carta sem caixa) ou tem fantasma — nos dois casos
# é dado ruim, e descartar aqui poupa a revisão manual de olhar foto por foto.
ESPERADO = {9, 10}

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "datasets" / "meu-setup"
DST = ROOT / "datasets" / "local"
for sub in ("images", "labels", "review"):
    (DST / sub).mkdir(parents=True, exist_ok=True)

detector = CardDetector("models/cards.pt", min_confidence=CONF)
# ids das classes na ordem do próprio modelo (o treino reusa essa ordem)
name_to_id = {name: i for i, name in detector.model.names.items()}

frames = sorted(SRC.glob("*.jpg"))
if not frames:
    sys.exit(f"nenhum frame em {SRC} — rode capture_auto.py primeiro")

annotated = 0
descartados = 0
for path in frames:
    frame = cv2.imread(str(path))
    if frame is None:
        continue
    dets = hand_instances(detector.detect(frame))
    codigos = {d.card.code for d in dets}
    if len(dets) not in ESPERADO or len(codigos) != len(dets):
        # contagem fora do esperado, ou dois rótulos iguais (uma das duas é
        # falsa, já que o baralho do teste não tem gêmeas)
        descartados += 1
        continue
    h, w = frame.shape[:2]
    lines = []
    for d in dets:
        x1, y1, x2, y2 = d.box
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        bw, bh = (x2 - x1) / w, (y2 - y1) / h
        lines.append(f"{name_to_id[d.card.code]} "
                     f"{cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    cv2.imwrite(str(DST / "images" / path.name), frame)
    (DST / "labels" / f"{path.stem}.txt").write_text("\n".join(lines))
    cv2.imwrite(str(DST / "review" / path.name), draw_boxes(frame, dets))
    annotated += 1
    print(f"{path.name}: {len(dets)} cartas")

print(f"\n{annotated} frames anotados, {descartados} descartados "
      f"(contagem fora de {sorted(ESPERADO)} ou rótulo repetido).")
print(f"AGORA: abra {DST / 'review'} e apague as fotos com anotação errada.")
print("Depois rode: python training/finetune_local.py")
