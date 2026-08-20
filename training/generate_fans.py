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
    """Fundo da cena — e ele importa muito mais do que parecia.

    Medido em 2026-08-20: os 12 fundos reais em `backgrounds/` são TODOS a
    mesma superfície de perto (brilho médio 117 em todos os 12). Ou seja, o
    treino sintético inteiro viu praticamente UM fundo. É a explicação
    estrutural de o modelo ler o logo *"10COC LEAGUE"* da parede da sala como
    `10C`/`QC` e textura de reboco como `5S 4D KS` — cenário com quinquilharia
    nunca apareceu no treino, e o que nunca apareceu não tem como ser aprendido
    como fundo.

    Duas mudanças, e as duas vêm do setup REAL descrito pelo usuário:

    1. Frames de sala vazia das gravações entraram em `backgrounds/`
       (`bg_sala_*.jpg`), o logo e o quadro-negro incluídos. Agora o leque é
       composto POR CIMA deles, e o modelo vê o distrator e a carta na mesma
       imagem — que é mais forte do que só ver o distrator sozinho num
       negativo.
    2. A cor chapada de reserva vai até 235, não mais até 110. "Na maior parte
       das vezes eu coloco a câmera virada para uma parede branca e lisa" — e o
       fundo chapado CLARO era exatamente o que faltava: carta branca sobre
       parede branca é o caso de menor contraste que existe, e o gerador só
       sabia produzir fundo escuro. O gradiente evita a chapa perfeita, que não
       existe em parede iluminada de verdade.
    """
    if bgs and random.random() < 0.70:
        bg = random.choice(bgs).astype(np.float32)
        bg *= random.uniform(0.6, 1.15)
        bg += np.random.uniform(-10, 10, 3)
        return np.clip(bg, 0, 255).astype(np.uint8)
    # NEUTRO com leve dominante, não cor aleatória por canal: sorteando os três
    # canais soltos saem paredes ciano e magenta, que não existem na sala do
    # usuário. O que existe é parede branca, bege e cinza — um NÍVEL, com um
    # desvio pequeno de tom.
    nivel = random.randint(20, 235)
    base = np.full((CANVAS_H, CANVAS_W, 3),
                   [np.clip(nivel + random.randint(-12, 12), 0, 255)
                    for _ in range(3)], np.float32)
    # queda de luz de um lado para o outro: parede lisa tem gradiente, não chapa
    g = np.linspace(random.uniform(0.80, 1.0), random.uniform(1.0, 1.20),
                    CANVAS_W, dtype=np.float32).reshape(1, -1, 1)
    if random.random() < 0.5:
        g = g[:, ::-1, :]            # a luz pode vir de qualquer um dos lados
    base = base * g
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
    # menor que isso a carta seguinte cobre o índice da anterior. Medido: com
    # passo de 0.03-0.06, 60% dos índices ficavam cobertos e cada imagem rendia
    # 3 rótulos em vez de 9.
    #
    # No leque ABERTO a rotação já afasta os topos, então o passo pode ser
    # menor; no FECHADO ele é o único mecanismo de exposição.
    #
    # LIMITE INFERIOR baixado de 0.20 para 0.12 em 2026-08-12, para aproximar a
    # DISTRIBUIÇÃO gerada da real. A grandeza comparável é adimensional:
    # distância entre índices vizinhos ÷ largura do índice (medida NOS RÓTULOS
    # gerados e nas detecções gravadas, já deduplicadas):
    #
    #   sintético antes: mediana 0.92, p05 0.70
    #   sintético agora: mediana 0.89, p05 0.67
    #   partidas reais:  mediana 0.74-0.78, p05 0.50
    #
    # Repare no tamanho do efeito: mexer no passo quase NÃO move a distribuição,
    # porque rotação e perspectiva pesam tanto quanto ele. O sintético continua
    # ~15% mais frouxo que o real. Se algum dia isso precisar fechar de verdade,
    # o parâmetro a atacar é a abertura/raio, não o passo — e meça nos rótulos,
    # não no parâmetro. Ver CLAUDE.md, "Comparar o aperto do leque".
    #
    # A mudança só é segura junto com o recorte de índice parcialmente coberto
    # em `parte_visivel`: sem ele, passo menor viraria rótulo DESCARTADO, que é
    # o envenenamento que este arquivo já documenta.
    step = (random.uniform(0.12, 0.32) * (1 - 0.45 * frac_spread)
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

    def parte_visivel(x1, y1, x2, y2, drawn_after):
        """Caixa do PEDAÇO do índice que as cartas posteriores não cobrem.

        Antes isto era um teste binário pelo CENTRO: centro coberto = rótulo
        descartado. Isso é a mesma armadilha que o recorte de borda logo abaixo
        existe para evitar — um índice PARCIALMENTE coberto continua visível na
        imagem, e região visível sem rótulo ensina o modelo que aquele padrão é
        fundo. E é o caso que mais importa: medido em 2026-08-12, no leque real
        os índices vizinhos se sobrepõem ~28% na mediana, condição que o
        gerador nunca produzia (ver CLAUDE.md, "O leque real é mais APERTADO").

        Recorta numa máscara do tamanho da caixa, apaga os polígonos das cartas
        desenhadas depois e devolve a caixa do que sobrou.
        """
        ix1, iy1 = int(np.floor(x1)), int(np.floor(y1))
        ix2, iy2 = int(np.ceil(x2)), int(np.ceil(y2))
        w, h = ix2 - ix1, iy2 - iy1
        if w < 2 or h < 2:
            return None
        m = np.ones((h, w), np.uint8)
        for j in drawn_after:
            p = (polys[j] - np.array([ix1, iy1], np.float32))
            cv2.fillPoly(m, [p.astype(np.int32)], 0)
        ys, xs = np.nonzero(m)
        if len(xs) == 0:
            return None
        # fração de ÁREA que sobrou: um filete de índice não identifica a carta
        # nem para um humano, e rotulá-lo seria ensinar ruído. 0.40 cobre a
        # faixa real (sobreposição mediana deixa ~73% visível) e exclui a cauda
        # ilegível (no p05 medido sobra ~24%).
        if len(xs) < 0.40 * w * h:
            return None
        return (ix1 + float(xs.min()), iy1 + float(ys.min()),
                ix1 + float(xs.max()), iy1 + float(ys.max()))

    for i, code in enumerate(codes):
        # SÓ o canto de cima é carta. O canto de baixo (invertido) NUNCA é
        # rotulado -> o modelo aprende a ignorá-lo (não conta 2x a última).
        # A caixa vem medida do molde (detect_corner_tl), não é fixa.
        x1, y1, x2, y2, pts = bbox_of(templates[code][1], mats[i])
        vis = parte_visivel(x1, y1, x2, y2, range(i + 1, n))
        if vis is None:
            DROP_STATS["coberto"] += 1
            continue
        x1, y1, x2, y2 = vis
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
    # O contador SÓ serve se for lido: três tentativas de deduzir por que a
    # detecção colapsava olhando as imagens falharam, e ele resolveu na
    # primeira. Se "coberto" dominar, as cartas estão empilhadas demais e o
    # modelo vai aprender com 3 índices em vez de 9.
    total = sum(DROP_STATS.values())
    print(f"pronto: {OUT}")
    print(f"{total} índices desenhados, "
          f"{DROP_STATS['rotulado'] / max(N_IMAGES, 1):.2f} rótulos por imagem")
    for motivo, n in DROP_STATS.most_common():
        print(f"  {motivo:16s} {n:7d}  {100 * n / max(total, 1):5.1f}%")


if __name__ == "__main__":
    main()
