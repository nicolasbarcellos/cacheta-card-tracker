"""Extrai dado REAL rotulado de uma partida GRAVADA, sem jogar de novo.

É o `capture_rotulado.py` feito offline. Lá o rótulo vem da mão que você digita
na ordem da esquerda para a direita; aqui ele vem do **gabarito revisado** da
partida — a carta certa de cada compra e de cada descarte, conferida no vídeo.
Nos dois casos o palpite do modelo é ignorado, que é o que quebra a
circularidade da pseudo-anotação (`auto_annotate.py` rotula com o modelo atual,
então a carta que ele erra nunca vira rótulo certo e nunca aprende).

A diferença é o preço: uma captura ao vivo custa uma sessão inteira segurando o
baralho, e as partidas gravadas já estão no disco. O que este script produz é
exatamente o que o projeto identificou como faltando — dado real **na condição
em que o modelo falha** e, de quebra, matéria-prima para um conjunto de
validação REAL (o `eval_classes.py` roda em sintético e deu K=100% no mesmo dia
em que o K♠ era lido como A♠ ao vivo).

## Como a verdade é reconstruída

    mão inicial  +  compras e descartes do gabarito  =  mão verdadeira em cada instante

A mão inicial vem da mão EXIBIDA no começo (leitura do modelo), mas não é aceita
no escuro: o gabarito PROVA parte dela — toda carta descartada sem ter sido
comprada antes estava lá — e o script recusa a partida se as duas se
contradisserem. As cartas que nunca foram jogadas o gabarito não prova, e é por
isso que existe `--mao-inicial`: confira o primeiro frame com o olho e informe.

## Por que a ordem sai por VOTAÇÃO no segmento, e não frame a frame

O rótulo de cada detecção vem da POSIÇÃO dela no leque (esquerda para a
direita), como no `capture_rotulado.py`. Só que aqui a mão verdadeira é um
CONJUNTO — a ordem física em que as cartas estão no leque não está no gabarito.

Casar posição com carta frame a frame, aceitando o palpite do modelo onde ele
bate, tem uma armadilha: quando o modelo lê a posição 3 como A♦ e o A♦
verdadeiro está na posição 7 (lido como 4♦), o casamento guloso premia o erro —
crava A♦ na posição 3 e deixa a posição 7 "por eliminação". Rótulo errado, e
justamente numa carta difícil.

Por isso o casamento é resolvido UMA VEZ por segmento (o trecho entre duas
jogadas, em que a mão não muda), somando a confiança de todos os frames do
segmento numa matriz posição × carta e escolhendo a atribuição de custo máximo
(designação exata por DP sobre máscara de bits — n ≤ 10). É a mesma ideia da
votação ponderada do `FanReader`: uma rajada de erro não derruba o acumulado.

## Guardas (alinhamento torto envenena o dataset inteiro)

- **contagem exata**: o frame precisa ter tantas detecções quanto a mão tem
  cartas — uma carta não detectada desloca todos os rótulos seguintes;
- **sem buraco** no espaçamento entre cantos vizinhos, mesmo motivo;
- **concordância mínima** do frame com a ordem do segmento;
- **margem em volta das jogadas**: o evento é emitido com atraso (`lock_frames`
  + votação, ~2 s), então a mão FÍSICA muda ANTES do `i` do gabarito. A janela
  antes de cada jogada é descartada, senão frames da mão nova receberiam os
  rótulos da mão velha;
- **ambiguidade por eliminação**: se duas posições ficam sem apoio nenhum na
  votação e as cartas que sobraram são diferentes, não há como saber qual vai
  onde — o segmento inteiro é recusado.

E, como no fluxo ao vivo, a última guarda é o olho: **olhe as imagens de
`review/`** antes de treinar. Verde é rótulo em que o modelo já concordava,
laranja é rótulo CORRIGIDO pelo gabarito — as laranjas são a razão de este
script existir, e também onde um erro de reconstrução apareceria.

Uso:
    python training/extrai_gravacao.py gravacoes/20260812-154737
    python training/extrai_gravacao.py gravacoes/... --por-segmento 20
    python training/extrai_gravacao.py gravacoes/... --mao-inicial "10H QD JH ..."
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cards import Card  # noqa: E402
from app.detector import Detection, hand_instances  # noqa: E402

ROOT = Path(__file__).resolve().parent

# Atraso entre a mão MUDAR de verdade e o evento ser emitido: `lock_frames`
# (30 frames) mais a votação do FanReader. Medido no projeto em ~2 s; 4 s dá
# folga, e frame descartado aqui é barato (sobram milhares).
MARGEM_ANTES = 4.0    # segundos antes da jogada que NÃO viram amostra
MARGEM_DEPOIS = 1.5   # segundos depois, até a mão nova assentar
GAP_MAX = 2.2         # buraco no espaçamento entre cantos = carta faltando
SALTO_Y = 2.0         # degrau vertical entre vizinhos, em alturas de caixa
# Fração dos rótulos do modelo que tem de bater com a ordem do segmento.
# 0.7, não 0.5: o perigo real não é o modelo errar uma carta (ele erra 7,6% na
# medição), é o frame ser de DEPOIS da mão mudar — aí os rótulos entram
# DESLOCADOS a partir do ponto em que a carta entrou, e metade do leque sai
# errada. A guarda de contagem já pega quase todos esses (a mão nova tem uma
# carta a mais ou a menos), e esta pega o resto.
MIN_CONCORDA = 0.7
MIN_FRAMES_SEG = 8    # segmento com menos frames válidos não vota confiável
MIN_APOIO = 0.60      # fração da confiança que a ordem escolhida deve explicar
BLOCO = 50            # frames por bloco de votação (acompanha o rearranjo)
MAX_TROCAS = 1        # discordâncias ambíguas toleradas por frame


def carrega_sessao(gravacao: Path):
    """(frames, maos) do sessao.jsonl. Frames sem vídeo (v<0) são inúteis."""
    frames, maos = [], []
    with open(gravacao / "sessao.jsonl", encoding="utf-8") as fh:
        for linha in fh:
            d = json.loads(linha)
            if d["t"] == "frame":
                frames.append(d)
            elif d["t"] == "mao" and d["cards"]:
                maos.append(d)
    return frames, maos


def mao_inicial(maos, jogadas, informada: str | None) -> list[str]:
    """A mão do começo da partida, conferida contra o que o gabarito prova."""
    if informada:
        mao = [Card.from_label(c).code for c in informada.split()]
    elif maos:
        mao = list(maos[0]["cards"])
    else:
        sys.exit("sem mão exibida na gravação — use --mao-inicial")

    # toda carta descartada sem ter sido comprada antes estava na mão inicial
    comprados: Counter = Counter()
    provadas: Counter = Counter()
    for j in jogadas:
        if j["tipo"] == "draw":
            comprados[j["carta"]] += 1
        elif comprados[j["carta"]] > 0:
            comprados[j["carta"]] -= 1
        else:
            provadas[j["carta"]] += 1

    falta = provadas - Counter(mao)
    if falta:
        sys.exit(f"mão inicial incompatível com o gabarito: ele prova "
                 f"{' '.join(sorted(falta.elements()))} na mão, e a mão "
                 f"informada é {' '.join(mao)}. Confira o vídeo e passe "
                 f"--mao-inicial.")
    nao_provadas = Counter(mao) - provadas
    print(f"mão inicial: {' '.join(mao)}")
    print(f"  o gabarito prova {sum(provadas.values())} delas; "
          f"{' '.join(sorted(nao_provadas.elements()))} vêm da leitura do "
          f"modelo — confira no vídeo se alguma for carta difícil")
    return mao


def segmentos(mao0, jogadas):
    """[(ts_ini, ts_fim, mão verdadeira)] — trechos em que a mão não muda.

    O trecho DEPOIS da última jogada fica de fora: o gabarito acaba ali, então
    dali em diante não há verdade nenhuma (a partida pode ter continuado).
    """
    segs, mao = [], Counter(mao0)
    anterior = 0.0
    for j in jogadas:
        segs.append((anterior, j["ts"], Counter(mao)))
        if j["tipo"] == "draw":
            mao[j["carta"]] += 1
        else:
            mao[j["carta"]] -= 1
            if mao[j["carta"]] <= 0:
                del mao[j["carta"]]
        anterior = j["ts"]
    return segs


def dets_do_frame(d) -> list[Detection]:
    return [Detection(card=Card.from_label(c), confidence=conf,
                      box=(x1, y1, x2, y2))
            for c, conf, x1, y1, x2, y2 in d["dets"]]


def alinhado(dets, n) -> bool:
    """Detecções em fileira, na contagem certa e sem buraco no meio."""
    if len(dets) != n:
        return False
    xs = [(d.box[0] + d.box[2]) / 2 for d in dets]
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    if gaps:
        meio = sorted(gaps)[len(gaps) // 2]
        if meio > 0 and max(gaps) > GAP_MAX * meio:
            return False

    # Salto VERTICAL entre índices vizinhos, em alturas de caixa. O leque é um
    # arco suave; uma detecção muito fora da fileira não é carta da mão — são
    # os dois casos que a auditoria encontrou envenenando rótulo: o canto de
    # BAIXO de uma carta virada, e uma carta largada na MESA dentro do quadro
    # (que o CLAUDE.md já registra como problema de enquadramento). Nos dois, a
    # contagem batia por coincidência (uma carta de verdade não detectada) e a
    # ordenação por x metia a intrusa no meio, deslocando os rótulos dali para
    # frente — 8♠ virava A♥.
    #
    # Medido nos 454 frames extraídos: mediana 0,28 e p99 1,25, depois um vão
    # até uma cauda de 3,5-4,3. Qualquer limiar de 1,5 a 3,0 corta os MESMOS
    # 3,7% dos frames, ou seja a cauda é população à parte e a escolha está num
    # platô, não numa borda. 2,0 é o meio dele.
    alturas = sorted(d.box[3] - d.box[1] for d in dets)
    h = alturas[len(alturas) // 2]
    ys = [(d.box[1] + d.box[3]) / 2 for d in dets]
    if h > 0 and any(abs(b - a) > SALTO_Y * h for a, b in zip(ys, ys[1:])):
        return False
    return True


def designa(peso, n):
    """Atribuição posição→carta de peso máximo (DP sobre máscara de bits).

    n ≤ 10, então 2^n estados é trivial. Exato de propósito: um guloso erraria
    exatamente no caso que este script existe para tratar — a carta que o
    modelo nunca acerta tem peso zero em toda posição e só se resolve por
    eliminação, o que depende da atribuição GLOBAL estar certa.
    """
    NEG = float("-inf")
    dp = [NEG] * (1 << n)
    escolha = [-1] * (1 << n)
    dp[0] = 0.0
    for mask in range(1 << n):
        if dp[mask] == NEG:
            continue
        pos = bin(mask).count("1")
        if pos == n:
            continue
        for c in range(n):
            if mask & (1 << c):
                continue
            novo = mask | (1 << c)
            valor = dp[mask] + peso[pos][c]
            if valor > dp[novo]:
                dp[novo] = valor
                escolha[novo] = c
    ordem, mask = [], (1 << n) - 1
    while mask:
        c = escolha[mask]
        ordem.append(c)
        mask &= ~(1 << c)
    return list(reversed(ordem))


def resolve_ordem(frames_seg, mao: Counter):
    """Ordem física (esquerda→direita) das cartas verdadeiras do segmento.

    Devolve (ordem, motivo_da_recusa). A votação soma CONFIANÇA, não contagem:
    é a mesma escolha do `FanReader`, medida no projeto — quando o modelo troca
    o naipe dentro da cor, ele erra com ~0.34 e acerta com ~0.85.
    """
    cartas = sorted(mao.elements())
    n = len(cartas)
    peso = [[0.0] * n for _ in range(n)]
    for dets in frames_seg:
        for pos, d in enumerate(dets):
            for c, carta in enumerate(cartas):
                if d.card.code == carta:
                    peso[pos][c] += d.confidence

    ordem_idx = designa(peso, n)
    ordem = [cartas[c] for c in ordem_idx]

    # Fração da confiança total que caiu nos pares (posição, carta) escolhidos.
    # É a medida de quanto a votação SUSTENTA esta atribuição: perto de 1, o
    # modelo já lia quase tudo certo e a designação só arrumou o resto; baixa,
    # a leitura do segmento é um borrão e a ordem virou palpite — e um palpite
    # de ordem envenena TODOS os rótulos do segmento, não só os corrigidos.
    total = sum(sum(linha) for linha in peso)
    apoio = sum(peso[pos][c] for pos, c in enumerate(ordem_idx))
    fracao = apoio / total if total else 0.0
    if fracao < MIN_APOIO:
        return None, f"apoio fraco ({fracao:.0%})"

    # posições que a votação não sustentou: a carta atribuída nunca foi lida
    # ali. Uma é o caso normal (a carta que o modelo erra sempre); duas cartas
    # DIFERENTES sem apoio é ambiguidade pura — não há como saber qual vai onde.
    sem_apoio = [ordem[pos] for pos in range(n)
                 if peso[pos][ordem_idx[pos]] == 0.0]
    if len(set(sem_apoio)) >= 2:
        return None, f"ambíguo ({' '.join(sem_apoio)} sem apoio)"
    detalhe = f"apoio {fracao:.0%}"
    if sem_apoio:
        detalhe += f", {sem_apoio[0]} por eliminação"
    return ordem, detalhe


def desalinhado(lidos, ordem) -> bool:
    """A leitura do frame é explicada igual (ou melhor) por um DESLOCAMENTO?

    A guarda mais importante do script, e a que faltava: rotular por posição
    supõe que a k-ésima detecção da esquerda é a k-ésima carta da mão. Basta
    UMA detecção sobrando — a carta que acabou de ser descartada, ainda no
    quadro, ou uma largada na mesa (problema de enquadramento que o CLAUDE.md
    já registra) — para que todos os rótulos dali para a direita entrem
    corridos de uma casa. Auditado nas imagens: era assim que um K♠ saía
    rotulado 9♠ e um 6♦ saía rotulado K♠.

    Contagem e buraco no leque não pegam esse caso (a contagem bate quando uma
    carta real deixa de ser detectada) e a concordância também não, porque
    metade dos rótulos continua batendo.

    Aqui a leitura é comparada com a ordem de referência de três jeitos: sem
    deslocamento, e com um deslocamento de uma casa a partir de cada ponto de
    corte (que é o efeito de uma detecção a mais ou a menos no meio). Se a
    versão deslocada explica tão bem quanto a direta, o frame é ambíguo e cai —
    mesmo com menos pares comparados, o empate já é suspeito o bastante.
    """
    n = len(ordem)
    direto = sum(1 for a, b in zip(lidos, ordem) if a == b)
    for corte in range(n):
        pre = sum(1 for i in range(corte) if lidos[i] == ordem[i])
        for suf in (sum(1 for i in range(corte, n - 1)
                        if lidos[i + 1] == ordem[i]),
                    sum(1 for i in range(corte, n - 1)
                        if lidos[i] == ordem[i + 1])):
            if pre + suf >= direto:
                return True
    return False


def ordem_encaixa(anterior, atual) -> bool:
    """A ordem nova é a antiga com UMA carta inserida ou removida?"""
    if anterior is None:
        return True
    curta, longa = ((anterior, atual) if len(anterior) <= len(atual)
                    else (atual, anterior))
    if len(longa) - len(curta) > 1:
        return False
    it = iter(longa)
    return all(any(c == x for x in it) for c in curta)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--gabarito", type=Path,
                    help="padrão: gabarito_corrigido.json, senão gabarito.json")
    ap.add_argument("--saida", type=Path,
                    help="padrão: training/datasets/real/<nome da gravação>")
    ap.add_argument("--por-segmento", type=int, default=40,
                    help="máximo de frames por segmento (padrão 40)")
    ap.add_argument("--intervalo", type=float, default=0.4,
                    help="segundos mínimos entre frames salvos (padrão 0.4)")
    ap.add_argument("--mao-inicial", help="ex.: \"10H QD JH 6S AD AH 9S KS 5D\"")
    ap.add_argument("--so-analise", action="store_true",
                    help="não abre o vídeo nem salva nada; só imprime o plano")
    ap.add_argument("--detalhe", action="store_true",
                    help="imprime a ordem resolvida de cada segmento")
    ap.add_argument("--margem-antes", type=float, default=MARGEM_ANTES,
                    help=f"segundos descartados antes de cada jogada "
                         f"(padrão {MARGEM_ANTES})")
    args = ap.parse_args()

    gab_path = args.gabarito or next(
        p for p in (args.gravacao / "gabarito_corrigido.json",
                    args.gravacao / "gabarito.json") if p.exists())
    jogadas = json.load(open(gab_path, encoding="utf-8"))["jogadas"]
    frames, maos = carrega_sessao(args.gravacao)
    print(f"{gab_path.name}: {len(jogadas)} jogadas | "
          f"{len(frames)} frames gravados")

    mao0 = mao_inicial(maos, jogadas, args.mao_inicial)
    segs = segmentos(mao0, jogadas)

    # ---- seleção dos frames, sem tocar no vídeo -------------------------
    plano = []          # (v, [(det, código)]) por frame escolhido
    recusas: Counter = Counter()
    corrigidas: Counter = Counter()
    recusadas_troca = [0]
    recusadas_desloc = [0]
    ordem_anterior = None
    idx = 0
    for ini, fim, mao in segs:
        ini, fim = ini + MARGEM_DEPOIS, fim - args.margem_antes
        if fim <= ini:
            recusas["janela curta"] += 1
            ordem_anterior = None
            continue
        n = sum(mao.values())
        candidatos = []
        while idx > 0 and frames[idx - 1]["ts"] >= ini:
            idx -= 1
        while idx < len(frames) and frames[idx]["ts"] < ini:
            idx += 1
        j = idx
        while j < len(frames) and frames[j]["ts"] <= fim:
            f = frames[j]
            j += 1
            if f["v"] < 0:
                continue
            dets = sorted(hand_instances(dets_do_frame(f)),
                          key=lambda d: (d.box[0] + d.box[2]) / 2)
            if not alinhado(dets, n):
                continue
            candidatos.append((f, dets))
        if len(candidatos) < MIN_FRAMES_SEG:
            recusas["poucos frames alinhados"] += 1
            ordem_anterior = None
            continue

        # A mão não muda dentro do segmento, mas a ORDEM dela muda: o jogador
        # reorganiza o leque no meio do turno. Uma ordem só para o segmento
        # inteiro fica velha a partir do rearranjo e rotula o resto deslocado —
        # foi medido na partida de 12/08, onde as correções AD->AH, AH->7S e
        # 7S->AD formavam um CICLO entre três cartas vizinhas, que é a
        # assinatura exata disso. Por isso a ordem é resolvida por BLOCO de
        # frames consecutivos: cada bloco tem votos de sobra e acompanha o
        # rearranjo.
        blocos = [candidatos[k:k + BLOCO]
                  for k in range(0, len(candidatos), BLOCO)]
        if len(blocos) > 1 and len(blocos[-1]) < MIN_FRAMES_SEG:
            rabo = blocos.pop()             # rabo curto não vota confiável
            blocos[-1] = blocos[-1] + rabo

        escolhidos, ultimo = [], -9e9
        for bloco in blocos:
            ordem, motivo = resolve_ordem([d for _, d in bloco], mao)
            if ordem is None:
                recusas[motivo.split(" (")[0]] += 1
                ordem_anterior = None   # o próximo não é mais vizinho deste
                if args.detalhe:
                    print(f"  [{bloco[0][0]['ts']:7.1f}s] RECUSADO {motivo} | "
                          f"mão {' '.join(sorted(mao.elements()))}")
                continue

            # A mão muda de UMA carta por jogada, e o jogador encaixa a nova
            # sem embaralhar o resto: a ordem seguinte deve conter a anterior
            # como subsequência. Não é motivo de recusa (o rearranjo existe e o
            # conjunto continua vindo do gabarito), mas é o primeiro lugar onde
            # um casamento errado apareceria — por isso fica visível.
            if args.detalhe:
                marca = ("" if ordem_encaixa(ordem_anterior, ordem)
                         else "  <<< ORDEM NÃO ENCAIXA")
                print(f"  [{bloco[0][0]['ts']:7.1f}s] {len(bloco):4d} frames | "
                      f"{motivo:28s} | {' '.join(ordem)}{marca}")
            ordem_anterior = ordem

            # espalha no tempo: frames vizinhos são quase idênticos e só
            # inflam o dataset com repetição
            for f, dets in bloco:
                if f["ts"] - ultimo < args.intervalo:
                    continue
                lidos = [d.card.code for d in dets]
                concorda = sum(1 for lido, c in zip(lidos, ordem) if lido == c)
                if concorda < MIN_CONCORDA * n:
                    continue
                # Discordância em que o rótulo do MODELO é outra carta DESTA
                # mão é ambígua: pode ser erro dele (A♦ e A♥ juntas confundem)
                # ou a ordem tendo mudado. Discordância em que o rótulo não
                # existe na mão é erro puro do modelo — é o caso do A♠, que
                # nunca esteve no jogo, e é exatamente o dado que se quer.
                # Uma ambígua passa; duas é o padrão do rearranjo, e o frame
                # inteiro cai.
                trocas = sum(1 for lido, c in zip(lidos, ordem)
                             if lido != c and mao.get(lido, 0) > 0)
                if trocas > MAX_TROCAS:
                    recusadas_troca[0] += 1
                    continue
                if desalinhado(lidos, ordem):
                    recusadas_desloc[0] += 1
                    continue
                ultimo = f["ts"]
                escolhidos.append((f, dets, ordem))

        if len(escolhidos) > args.por_segmento:
            passo = len(escolhidos) / args.por_segmento
            escolhidos = [escolhidos[int(k * passo)]
                          for k in range(args.por_segmento)]
        for f, dets, ordem in escolhidos:
            plano.append((f["v"], list(zip(dets, ordem))))
            for d, c in zip(dets, ordem):
                if d.card.code != c:
                    corrigidas[f"{d.card.code}->{c}"] += 1

    print(f"\n{len(segs)} segmentos | {len(plano)} frames selecionados | "
          f"recusados: {recusadas_troca[0]} por ambiguidade, "
          f"{recusadas_desloc[0]} por deslocamento")
    if recusas:
        print("blocos recusados:")
        for motivo, n in recusas.most_common():
            print(f"  {motivo}: {n}")
    total_rot = sum(len(r) for _, r in plano)
    print(f"{total_rot} rótulos, dos quais {sum(corrigidas.values())} "
          f"CORRIGIDOS pelo gabarito "
          f"({100 * sum(corrigidas.values()) / max(total_rot, 1):.1f}%)")
    for erro, n in corrigidas.most_common(15):
        print(f"  {erro}: {n}")
    if args.so_analise or not plano:
        return

    # ---- uma passada sequencial pelo vídeo ------------------------------
    dst = args.saida or (ROOT / "datasets" / "real" / args.gravacao.name)
    for sub in ("images", "labels", "review"):
        (dst / sub).mkdir(parents=True, exist_ok=True)
    # o nome da classe vira id pela ordem do modelo — a mesma que o treino usa
    from ultralytics import YOLO  # import tardio: pesado
    nomes = YOLO("models/cards.pt").names
    name_to_id = {nome: i for i, nome in nomes.items()}

    por_v = dict(plano)
    alvos = sorted(por_v)
    # quais frames tiveram rótulo corrigido, e para quê. É por onde se audita o
    # dataset depois: são as amostras que o modelo atual erraria, ou seja as
    # únicas que ensinam algo novo — e também onde um erro de reconstrução
    # apareceria. Abra o review/ desses frames antes de treinar.
    auditoria: dict[str, list[str]] = {}
    cap = cv2.VideoCapture(str(args.gravacao / "mao.avi"))
    salvos, v = 0, 0
    # sequencial com grab(): buscar (seek) num MJPG de gigabytes é ordens de
    # grandeza mais lento do que pular frame a frame sem decodificar
    for alvo in alvos:
        while v < alvo:
            if not cap.grab():
                break
            v += 1
        ok, frame = cap.read()
        if not ok:
            break
        v += 1
        h, w = frame.shape[:2]
        linhas, view = [], frame.copy()
        for d, code in por_v[alvo]:
            x1, y1, x2, y2 = (int(b) for b in d.box)
            linhas.append(f"{name_to_id[code]} "
                          f"{(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                          f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
            cor = (0, 255, 0) if d.card.code == code else (0, 165, 255)
            cv2.rectangle(view, (x1, y1), (x2, y2), cor, 2)
            cv2.putText(view, code, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, cor, 2)
        nome = f"{args.gravacao.name}_{alvo:06d}"
        trocas = [f"{d.card.code}->{c}" for d, c in por_v[alvo]
                  if d.card.code != c]
        if trocas:
            auditoria[f"{nome}.jpg"] = trocas
        cv2.imwrite(str(dst / "images" / f"{nome}.jpg"), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        (dst / "labels" / f"{nome}.txt").write_text("\n".join(linhas))
        cv2.imwrite(str(dst / "review" / f"{nome}.jpg"), view,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])
        salvos += 1
        if salvos % 50 == 0:
            print(f"  {salvos}/{len(alvos)} frames", flush=True)
    cap.release()
    (dst / "correcoes.json").write_text(
        json.dumps(auditoria, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{salvos} frames salvos em {dst}")
    print(f"{len(auditoria)} deles têm rótulo corrigido — listados em "
          f"{dst / 'correcoes.json'}")
    print("laranja no review = rótulo CORRIGIDO pelo gabarito (é o que importa)")


if __name__ == "__main__":
    main()
