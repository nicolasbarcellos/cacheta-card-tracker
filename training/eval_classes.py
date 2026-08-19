"""Mede acerto de CLASSE por índice, com taxonomia de erro.

É o instrumento de comparação entre modelos: rode no modelo atual e no backup
para saber se um retreino melhorou ou piorou, em vez de confiar no mAP interno
do Ultralytics — que mede o modelo contra o dataset que o treinou e sempre
parece ótimo.

Como casa predição com verdade: cada PREDIÇÃO é atribuída ao índice verdadeiro
mais próximo do seu centro (e não o contrário). Num leque apertado o passo
entre cantos vizinhos é menor que a própria caixa do índice — se cada verdade
puxasse a predição mais próxima dentro de um raio, ela roubaria a predição da
carta vizinha e a métrica mediria ruído. Essa inversão é o que impede isso.

Não usa IoU de propósito: mudanças na caixa do índice (como a correção do pip
do naipe) alterariam o IoU sem alterar a classificação, misturando erro de
geometria com erro de classe. O viés de centro é reportado à parte, e serve
como diagnóstico próprio: viés grande em y significa que a caixa que o modelo
aprendeu não é a que o gerador rotula.

Reporta, além do acerto geral:
  - erro por TIPO (naipe na mesma cor, valor, ambos) — a família dominante diz
    onde atacar;
  - acerto por ABERTURA do leque, porque uma média global esconde um modelo
    que vai bem no leque fechado e mal no aberto;
  - acerto por rank e por naipe, e as piores classes.

IMPORTANTE: compara modelos sempre no MESMO conjunto de validação. Trocar o
dataset entre as medições invalida a comparação — o conjunto novo pode ser
mais fácil ou mais difícil que o antigo.

E prefira medir num conjunto REAL: rodando só em sintético, este script já
aprovou (K = 100%) um modelo que errava justamente o K♠ na mesa. Passe uma
partida extraída por `extrai_gravacao.py` que NÃO tenha entrado no treino.

Uso: python training/eval_classes.py <modelo.pt> [n_imagens] [dataset]
     python training/eval_classes.py models/cards.pt 400 training/datasets/real/20260811-211614
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

MODEL_PATH = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "models" / "cards.pt")
N_IMAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 150
# Terceiro argumento: um dataset REAL (ex.: training/datasets/real/<partida>,
# produzido por extrai_gravacao.py). Sem ele, mede no sintético — e aí a
# medição herda o defeito que o projeto já documentou: em 2026-08-12 este
# script deu K=100% no MESMO dia em que o K♠ era lido como A♠ na mesa, porque
# o sintético não gera aquela condição. Um dataset real de uma partida que o
# modelo NÃO treinou é o único conjunto que mede o que importa.
DATASET = Path(sys.argv[3]) if len(sys.argv) > 3 else None
sys.argv = [sys.argv[0]]

from finetune_local import SYNTH, collect, split_pairs  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from app.config import config  # noqa: E402

CONF = 0.10
DIST_MAX = 90.0            # px: acima disso a predição é lixo, não é a carta
PRETO, VERMELHO = {"S", "C"}, {"H", "D"}


def cor(suit):
    return "preto" if suit in PRETO else "vermelho"


def tipo_erro(verdade, predito):
    rv, sv = verdade[:-1], verdade[-1]
    rp, sp = predito[:-1], predito[-1]
    if rv == rp and sv != sp:
        return "naipe mesma cor" if cor(sv) == cor(sp) else "naipe outra cor"
    if rv != rp and sv == sp:
        return "valor"
    return "valor+naipe"


model = YOLO(MODEL_PATH)
names = model.names

if DATASET is not None:
    # dataset real: TODAS as imagens revisadas são validação — ele não treinou
    # este conjunto (é o holdout), então não há o que separar
    val = collect(DATASET, needs_review=True)[:N_IMAGES]
    if not val:
        sys.exit(f"nenhuma imagem revisada em {DATASET}")
    fonte = f"{DATASET.name} (REAL)"
else:
    pares = collect(SYNTH)
    if not pares:
        sys.exit(f"nenhuma imagem em {SYNTH} — rode generate_fans.py")
    _treino, val = split_pairs(pares, seed=42)
    val = val[:N_IMAGES]
    fonte = f"sintético (de {len(pares)} geradas)"
print(f"modelo: {MODEL_PATH}")
print(f"validacao: {len(val)} imagens — {fonte}\n", flush=True)

# abertura do leque por imagem: num leque FECHADO os índices ficam quase na
# mesma altura; num ABERTO descrevem um arco. A dispersão vertical é o proxy.
por_abertura: list = []
total = achados = certos = 0
erros: Counter = Counter()
por_classe: dict = defaultdict(lambda: [0, 0])
confusao: Counter = Counter()
dx_all: list = []
dy_all: list = []

for k, (img_path, label_path) in enumerate(val):
    img = cv2.imread(str(img_path))
    if img is None:
        continue
    h, w = img.shape[:2]
    gts = []
    for linha in label_path.read_text().strip().splitlines():
        partes = linha.split()
        if len(partes) != 5:
            continue
        cid = int(partes[0])
        cx, cy, bw, bh = (float(v) for v in partes[1:])
        gts.append([names[cid], cx * w, cy * h, bw * w, bh * h])
    if not gts:
        continue

    res = model.predict(img, conf=CONF, imgsz=config.detect_imgsz,
                        agnostic_nms=False, verbose=False)[0]

    atribuidas: dict = defaultdict(list)
    for b in res.boxes:
        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
        pcx, pcy = (x1 + x2) / 2, (y1 + y2) / 2
        melhor_i, melhor_d = None, DIST_MAX
        for i, g in enumerate(gts):
            d = ((g[1] - pcx) ** 2 + (g[2] - pcy) ** 2) ** 0.5
            if d < melhor_d:
                melhor_i, melhor_d = i, d
        if melhor_i is not None:
            atribuidas[melhor_i].append(
                (names[int(b.cls)], float(b.conf), pcx, pcy))

    ys = [g[2] for g in gts]
    abertura = (max(ys) - min(ys)) / h if len(ys) > 1 else 0.0

    for i, g in enumerate(gts):
        code = g[0]
        total += 1
        por_classe[code][1] += 1
        cands = atribuidas.get(i)
        if not cands:
            erros["nao detectado"] += 1
            por_abertura.append((abertura, False))
            continue
        achados += 1
        melhor = max(cands, key=lambda p: p[1])
        dx_all.append(melhor[2] - g[1])
        dy_all.append(melhor[3] - g[2])
        acertou = melhor[0] == code
        por_abertura.append((abertura, acertou))
        if acertou:
            certos += 1
            por_classe[code][0] += 1
        else:
            erros[tipo_erro(code, melhor[0])] += 1
            confusao[(code, melhor[0])] += 1

    if (k + 1) % 25 == 0:
        print(f"  {k + 1}/{len(val)} imagens...", flush=True)

print(f"\n=== {total} indices avaliados ===")
print(f"  detectados:        {achados:5d}  ({100*achados/total:.1f}%)")
print(f"  classe correta:    {certos:5d}  ({100*certos/total:.1f}% do total, "
      f"{100*certos/achados:.1f}% dos detectados)")
print("\n  erros por tipo:")
for tipo, n in erros.most_common():
    print(f"    {tipo:<18s} {n:5d}  ({100*n/total:.1f}%)")

if dy_all:
    print(f"\n  vies de centro predicao-verdade: "
          f"dx_medio={sum(dx_all)/len(dx_all):+.1f}px "
          f"dy_medio={sum(dy_all)/len(dy_all):+.1f}px")

if por_abertura:
    faixas = [(0.00, 0.10, "fechado   "), (0.10, 0.20, "medio     "),
              (0.20, 0.35, "aberto    "), (0.35, 9.99, "bem aberto")]
    print("\n  acerto por ABERTURA do leque:")
    for lo, hi, nome in faixas:
        sel = [ok for ab, ok in por_abertura if lo <= ab < hi]
        if sel:
            print(f"    {nome}  {100*sum(sel)/len(sel):5.1f}%  (n={len(sel)})")

print("\n  15 piores classes (>= 10 amostras):")
piores = sorted(((c[0] / c[1], code, c[1]) for code, c in por_classe.items()
                 if c[1] >= 10))
for acc, code, n in piores[:15]:
    print(f"    {code:>3s}  {100*acc:5.1f}%  (n={n})")

por_rank: dict = defaultdict(lambda: [0, 0])
por_naipe: dict = defaultdict(lambda: [0, 0])
for code, (ok, n) in por_classe.items():
    por_rank[code[:-1]][0] += ok
    por_rank[code[:-1]][1] += n
    por_naipe[code[-1]][0] += ok
    por_naipe[code[-1]][1] += n
print("\n  acerto por RANK:")
for rank, (ok, n) in sorted(por_rank.items(), key=lambda kv: kv[1][0] / kv[1][1]):
    print(f"    {rank:>3s}  {100*ok/n:5.1f}%  (n={n})")
print("\n  acerto por NAIPE:")
for s, (ok, n) in sorted(por_naipe.items(), key=lambda kv: kv[1][0] / kv[1][1]):
    print(f"    {s:>3s}  {100*ok/n:5.1f}%  (n={n})")

print("\n  10 confusoes mais frequentes:")
for (v, p), n in confusao.most_common(10):
    print(f"    {v:>3s} -> {p:>3s}  {n:4d}   [{tipo_erro(v, p)}]")

mesma_cor = erros["naipe mesma cor"]
print(f"\n  >>> troca de naipe na MESMA COR: {mesma_cor} "
      f"({100*mesma_cor/total:.1f}% dos indices) <<<")
