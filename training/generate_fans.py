"""Gera leques sintéticos REALISTAS (apertados) a partir dos moldes.

v2 — corrige o sim-to-real gap da v1:
- leque apertado: cartas muito sobrepostas, só a listra + o índice do canto
  superior-esquerdo aparece (como num leque de verdade); a última carta
  mostra a face inteira.
- rótulo = SÓ o canto superior-esquerdo visível de cada carta (+ canto
  inferior-direito da última). Nada de rótulo em canto coberto.
- realismo: perspectiva por carta, brilho/sombra, sombra entre cartas,
  desfoque de movimento, granulado de câmera, fundos reais da mesa.

Uso: python training/generate_fans.py [n_imagens]   (padrão: 2000)
Saída: training/datasets/synthetic/{images,labels}/
"""
import random
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cards import RANKS, SUITS  # noqa: E402

N_IMAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
CANVAS_W, CANVAS_H = 1280, 720
TPL_W, TPL_H = 250, 350
# fallback: índice (valor+naipe) do canto superior-esquerdo no molde 250x350.
# Só entra em ação se a medição por molde falhar — ver detect_corner_tl().
DEFAULT_CORNER_TL = np.array([[10, 12], [56, 12], [56, 96], [10, 96]],
                             np.float32)

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
BACKGROUNDS = ROOT / "backgrounds"
OUT = ROOT / "datasets" / "synthetic"

# Por que cada carta desenhada NÃO virou rótulo. Serve para ajustar a
# geometria do leque: se "coberto" domina, as cartas estão empilhadas demais e
# o modelo aprende com 3 índices em vez de 9.
DROP_STATS: Counter = Counter()


def reset_out():
    import shutil
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "images").mkdir(parents=True)
    (OUT / "labels").mkdir(parents=True)


ALL_CODES = sorted(f"{r}{s}" for r in RANKS for s in SUITS)
NAME_TO_ID = {c: i for i, c in enumerate(ALL_CODES)}

# Ranks que o modelo mais erra, medidos em 1725 índices de validação:
#   8 = 82,4%   5 = 86,7%   3 = 89,0%   A = 91,1%   (Q = 98,2% no outro extremo)
# As confusões dominantes são entre eles — 5→3, A↔4, 8→6 — e a A↔4 sobrevive
# ao vivo: medido na câmera, uma vaga do 4♦ acumulou A♦=16,1 contra 4D=7,1.
# Sorteá-los com peso maior faz o treino gastar mais amostras onde erra.
RANKS_FRACOS = {"A", "3", "4", "5", "8"}
PESO_RANK_FRACO = 2.5


def escolhe_codigos(templates, n):
    """Sorteia n cartas distintas, com peso maior para os ranks fracos."""
    pool = list(templates)
    pesos = [PESO_RANK_FRACO if code[:-1] in RANKS_FRACOS else 1.0
             for code in pool]
    escolhidos = []
    for _ in range(min(n, len(pool))):
        i = random.choices(range(len(pool)), weights=pesos, k=1)[0]
        escolhidos.append(pool.pop(i))
        pesos.pop(i)
    return escolhidos


def detect_corner_tl(img):
    """Mede a caixa do índice (valor+naipe) do canto superior-esquerdo.

    Uma caixa fixa erra quando o molde está desalinhado — nem todo molde saiu
    do capture_deck.py com a carta no mesmo lugar, alguns ficaram com sobra de
    fundo da mesa (4C e AC, p.ex.), e aí a caixa fixa cai no fundo em vez de
    cair no valor. Medindo no próprio molde, a caixa acompanha a carta.

    Como: acha a tinta (pixel que destoa do papel, preto ou vermelho) e
    agrupa o bloco do índice — o valor mais o pip logo abaixo — parando antes
    dos pips centrais, separados por um vão bem maior. Contorno que ENCOSTA na
    borda da janela é aresta da carta, mesa ou carta vizinha, não índice.
    Se a medição não convencer, cai no DEFAULT_CORNER_TL.
    """
    win_w, win_h = int(TPL_W * 0.34), int(TPL_H * 0.40)
    region = img[:win_h, :win_w]
    val = cv2.split(cv2.cvtColor(region, cv2.COLOR_BGR2HSV))[2]
    # papel = mediana só dos pixels claros: imune à sobra de mesa escura
    paper = np.median(region[val >= np.percentile(val, 60)].reshape(-1, 3),
                      axis=0)
    dist = np.linalg.norm(region.astype(np.float32) - paper, axis=2)
    ink = (dist > 55).astype(np.uint8) * 255

    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        if cv2.contourArea(c) <= 25:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if x == 0 or y == 0 or x + w >= win_w or y + h >= win_h:
            continue
        boxes.append((x, y, w, h))
    if not boxes:
        return DEFAULT_CORNER_TL
    boxes.sort(key=lambda b: b[1])

    group = [boxes[0]]
    for b in boxes[1:]:
        if b[1] - max(g[1] + g[3] for g in group) > 22:
            break
        group.append(b)

    pad = 3
    x1 = max(min(b[0] for b in group) - pad, 0)
    y1 = max(min(b[1] for b in group) - pad, 0)
    x2 = min(max(b[0] + b[2] for b in group) + pad, win_w)
    y2 = min(max(b[1] + b[3] for b in group) + pad, win_h)
    if not (15 <= x2 - x1 <= win_w * 0.95 and 25 <= y2 - y1 <= win_h * 0.95):
        return DEFAULT_CORNER_TL
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.float32)


def load_templates():
    """code -> (molde, caixa do índice medida nele)."""
    t = {}
    for p in TEMPLATES.glob("*.png"):
        img = cv2.imread(str(p))
        if img is not None and p.stem in NAME_TO_ID:
            card = cv2.resize(img, (TPL_W, TPL_H))
            t[p.stem] = (card, detect_corner_tl(card))
    return t


def load_backgrounds():
    bgs = []
    for p in list(BACKGROUNDS.glob("*.jpg")) + list(BACKGROUNDS.glob("*.png")):
        img = cv2.imread(str(p))
        if img is not None:
            bgs.append(cv2.resize(img, (CANVAS_W, CANVAS_H)))
    return bgs


def random_background(bgs):
    if bgs and random.random() < 0.85:
        bg = random.choice(bgs).astype(np.float32)
        bg *= random.uniform(0.6, 1.15)
        bg += np.random.uniform(-10, 10, 3)
        return np.clip(bg, 0, 255).astype(np.uint8)
    base = np.full((CANVAS_H, CANVAS_W, 3),
                   [random.randint(20, 110) for _ in range(3)], np.uint8)
    noisy = np.clip(base + np.random.normal(0, 8, base.shape), 0, 255)
    return noisy.astype(np.uint8)


def jitter_card(img):
    img = img.astype(np.float32)
    img *= random.uniform(0.65, 1.15)                 # brilho
    img += np.random.uniform(-10, 10, 3)              # tom
    # gradiente de iluminação (uma borda mais clara)
    g = np.linspace(random.uniform(0.8, 1.0), random.uniform(1.0, 1.2),
                    img.shape[1], dtype=np.float32).reshape(1, -1, 1)
    img = np.clip(img * g, 0, 255)
    return img.astype(np.uint8)


def perspective_matrix(scale, pivot, angle_deg):
    """Molde em pé -> posição, com leve perspectiva e giro em torno do pivô."""
    src = np.array([[0, 0], [TPL_W, 0], [TPL_W, TPL_H], [0, TPL_H]], np.float32)
    warp = random.uniform(0, 0.05)
    dst = np.array([
        [TPL_W * random.uniform(0, warp), TPL_H * random.uniform(0, warp)],
        [TPL_W * (1 - random.uniform(0, warp)), TPL_H * random.uniform(0, warp)],
        [TPL_W * (1 - random.uniform(0, warp)),
         TPL_H * (1 - random.uniform(0, warp))],
        [TPL_W * random.uniform(0, warp),
         TPL_H * (1 - random.uniform(0, warp))]], np.float32)
    persp = cv2.getPerspectiveTransform(src, dst)
    place = np.array([[scale, 0, pivot[0] - TPL_W * scale / 2],
                      [0, scale, pivot[1] - TPL_H * scale / 2],
                      [0, 0, 1]], np.float32)
    rot = np.vstack([cv2.getRotationMatrix2D(pivot, angle_deg, 1.0),
                     [0, 0, 1]]).astype(np.float32)
    return rot @ place @ persp


def bbox_of(corner, m):
    pts = cv2.perspectiveTransform(corner.reshape(1, -1, 2), m)[0]
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    return float(x1), float(y1), float(x2), float(y2), pts


def compose_fan(templates, bgs):
    canvas = random_background(bgs).astype(np.float32)
    n = random.choice([6, 7, 8] + [9] * 10 + [10] * 3)
    codes = escolhe_codigos(templates, n)
    n = len(codes)

    # ABERTURA: medido no setup real, um leque de 9 cartas segurado na mão
    # abre 150-180 graus, não 28-52. Com a faixa antiga o modelo só via cartas
    # quase em pé; ao vivo, as das pontas chegavam deitadas ou de cabeça para
    # baixo e simplesmente não eram detectadas — 3 detecções para 9 cartas.
    # A faixa cobre o leque fechado E o aberto, porque os dois acontecem.
    total_spread = random.uniform(25, 150)
    frac_spread = (total_spread - 25) / 125

    # ESCALA: o leque tem de PREENCHER o quadro, como preenche ao vivo. Medido
    # na câmera real, a carta ocupa ~16% da largura do frame, o que dá scale
    # ~0.8 neste canvas. Encolher o leque para ele "caber" seria afastar ainda
    # mais o sintético do real — quem lida com o que passa da borda é o recorte
    # do rótulo, mais abaixo.
    scale = random.uniform(0.55, 1.0)

    # PASSO: é o deslocamento entre cartas que EXPÕE o índice. O índice tem
    # ~44px de largura no molde, ou seja ~0.18 da largura da carta — com passo
    # menor que isso a carta seguinte cobre o índice da anterior e a imagem sai
    # sem rótulo. Medido: com passo de 0.03-0.06, 60% dos índices ficavam
    # cobertos e cada imagem rendia 3 rótulos em vez de 9.
    #
    # No leque ABERTO a rotação já afasta os topos, então o passo pode ser
    # menor; no FECHADO ele é o único mecanismo de exposição.
    step = (random.uniform(0.20, 0.32) * (1 - 0.45 * frac_spread)
            * TPL_W * scale)

    # INCLINAÇÃO do leque inteiro: a mão raramente segura na vertical exata.
    tilt = random.uniform(-20, 20)

    # GEOMETRIA: o punho é o pivô e fica na BORDA DE BAIXO do quadro; as cartas
    # irradiam para cima. Antes o pivô caía solto no meio do canvas e, com
    # abertura grande, as cartas das pontas giravam para baixo e saíam pelo
    # rodapé — o corner ficava coberto ou fora, e a imagem rendia 3-4 rótulos
    # em vez de 9. Ancorar o pivô embaixo é o que faz os 9 índices aparecerem,
    # como aparecem na mão de verdade.
    cx = random.uniform(CANVAS_W * 0.35, CANVAS_W * 0.65)
    pivot_y = CANVAS_H * random.uniform(0.75, 0.95)
    raio = TPL_H * scale * random.uniform(0.5, 0.9)   # punho -> centro da carta
    cy = pivot_y - raio
    pivot = (cx, pivot_y)

    mats = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        angle = (-total_spread / 2 + total_spread * frac + tilt
                 + random.uniform(-1, 1))
        base = (cx - step * (n - 1) / 2 + step * i, cy)
        mats.append(perspective_matrix(scale, base, -angle))

    # desenha da esquerda p/ direita (as de cima cobrem as de baixo)
    for i, code in enumerate(codes):
        card = jitter_card(templates[code][0])
        warped = cv2.warpPerspective(card.astype(np.float32), mats[i],
                                     (CANVAS_W, CANVAS_H))
        mask = cv2.warpPerspective(np.full((TPL_H, TPL_W), 255, np.uint8),
                                   mats[i], (CANVAS_W, CANVAS_H))
        # sombrinha da carta anterior
        sh = cv2.GaussianBlur(mask, (21, 21), 0).astype(np.float32) / 255
        canvas *= (1 - 0.12 * sh[..., None])
        m3 = mask > 127
        canvas[m3] = warped[m3]

    # rótulos: canto TL de cada carta (visível se nenhuma carta POSTERIOR
    # o cobre) + canto BR só da última
    labels = []
    polys = [cv2.perspectiveTransform(
        np.array([[[0, 0], [TPL_W, 0], [TPL_W, TPL_H], [0, TPL_H]]], np.float32),
        mats[i])[0] for i in range(n)]

    def visible(pts, drawn_after):
        c = tuple(pts.mean(axis=0))
        for j in drawn_after:
            if cv2.pointPolygonTest(polys[j].astype(np.float32), c, False) >= 0:
                return False
        return True

    for i, code in enumerate(codes):
        # SÓ o canto de cima é carta. O canto de baixo (invertido) NUNCA é
        # rotulado -> o modelo aprende a ignorá-lo (não conta 2x a última).
        # A caixa vem medida do molde (detect_corner_tl), não é fixa.
        x1, y1, x2, y2, pts = bbox_of(templates[code][1], mats[i])
        if not visible(pts, range(i + 1, n)):
            DROP_STATS["coberto"] += 1
            continue
        # RECORTA na borda em vez de descartar. Descartar era pior que perder
        # a amostra: o índice continua VISÍVEL na imagem, e uma região visível
        # sem rótulo ensina o modelo que aquele padrão é fundo — exatamente o
        # padrão que ele precisa detectar. Com o leque aberto, que é o caso
        # real, muitas cartas encostam na borda.
        vx1, vy1 = max(x1, 0.0), max(y1, 0.0)
        vx2, vy2 = min(x2, CANVAS_W - 1.0), min(y2, CANVAS_H - 1.0)
        if (vx2 - vx1) < 8 or (vy2 - vy1) < 12:
            DROP_STATS["pequeno"] += 1
            continue
        if (vx2 - vx1) * (vy2 - vy1) < 0.5 * (x2 - x1) * (y2 - y1):
            DROP_STATS["fora do quadro"] += 1
            continue          # mais da metade fora do quadro: já não é o índice
        DROP_STATS["rotulado"] += 1
        labels.append(f"{NAME_TO_ID[code]} "
                      f"{(vx1 + vx2) / 2 / CANVAS_W:.6f} "
                      f"{(vy1 + vy2) / 2 / CANVAS_H:.6f} "
                      f"{(vx2 - vx1) / CANVAS_W:.6f} "
                      f"{(vy2 - vy1) / CANVAS_H:.6f}")

    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    # realismo final: desfoque de movimento e granulado
    if random.random() < 0.4:
        k = random.choice([3, 5])
        canvas = cv2.GaussianBlur(canvas, (k, k), 0)
    if random.random() < 0.5:
        canvas = np.clip(canvas.astype(np.float32)
                         + np.random.normal(0, random.uniform(3, 10),
                                            canvas.shape), 0, 255).astype(np.uint8)
    return canvas, labels


def main():
    templates = load_templates()
    if len(templates) < 40:
        sys.exit(f"só {len(templates)} moldes — rode capture_deck.py")
    bgs = load_backgrounds()
    reset_out()
    print(f"{len(templates)} moldes, {len(bgs)} fundos; gerando {N_IMAGES}...")
    for i in range(N_IMAGES):
        canvas, labels = compose_fan(templates, bgs)
        if not labels:
            continue
        cv2.imwrite(str(OUT / "images" / f"fan_{i:05d}.jpg"), canvas,
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
        (OUT / "labels" / f"fan_{i:05d}.txt").write_text("\n".join(labels))
        if (i + 1) % 250 == 0:
            print(f"{i + 1}/{N_IMAGES}")
    print(f"pronto: {OUT}")


if __name__ == "__main__":
    main()
