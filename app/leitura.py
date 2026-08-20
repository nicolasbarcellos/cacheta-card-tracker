"""A nota deste projeto: a mão na TELA é a mão real, agora?

Desde 2026-08-19 o produto é um só — ler a mão. Compra e descarte saíram de
escopo, e com eles saiu a única nota que o repositório sabia dar
(`app/scoring.py`, que conta jogadas acertadas). Este módulo é o instrumento da
métrica nova, e ele mede três coisas contra uma partida gravada:

- **atraso** — segundos entre a leitura viva mostrar um conjunto e a TELA passar
  a mostrá-lo. É o que o jogador sente como "demorou";
- **contradição** — % dos frames em que uma carta está visível no leque com
  confiança alta e NÃO está na tela. É o que o jogador vê como "está errado";
- **excesso** — o espelho da contradição: % dos frames em que a TELA mostra uma
  carta que o quadro não mostrou em nenhum dos últimos `fan_window` frames.
  Faltava, e a falta era grave: medida a partida de 20/08, **44,5% dos frames
  exibiam 17 cartas**, com a mesma carta repetida três vezes — e os outros três
  números saíram bons, porque contradição só cobra carta FALTANDO na tela e
  ordem só compara quando os conjuntos batem. Um leitor que mostra tudo o que
  já viu tinha nota ótima;
- **trocas** — quantas vezes a mão exibida mudou. Acima do número de jogadas da
  partida, o excesso é tremor.

E mais três números que não são a nota mas explicam quase todo o resto:

- **cobertura** — DOS FRAMES EM QUE O MODELO VIU ALGUMA CARTA, em quantos havia
  mão na tela. O denominador é a ressalva inteira, e é a diferença entre um
  número útil e um número enganoso: medida sobre TODOS os frames, a cobertura
  das duas partidas de 19/08 dá 16,6% e 19,4%, e parece dizer que o leque passa
  82% do tempo fora do quadro. Não passa — a gravação é que ficou rodando com
  ninguém na frente da câmera (numa delas a partida inteira cabe nos 3 primeiros
  minutos de 12,8). Contei essa leitura errada como achado neste arquivo antes
  de olhar a linha do tempo;
- **atividade** — que fração da gravação teve carta na frente da câmera. É o
  denominador acima, publicado à parte justamente para não se confundir de novo
  com defeito do leitor;
- **ordem** — % dos frames em que a tela tem as cartas certas na ordem errada.

Estas contas viviam em dois scripts soltos no diretório temporário de uma
sessão (`mede_atraso.py`, `contradicoes.py`). Os números que o CLAUDE.md
publica saíram de lá — o que significa que a métrica oficial do projeto não era
reproduzível a partir de um `git clone`. Está aqui, e em `app/` e não em
`scripts/`, pela mesma razão que o `app/replay.py`: é código puro e carrega uma
promessa que precisa de teste (`tests/test_leitura.py`).

Roda o pipeline DE VERDADE (`app.main.process_frame`), nunca uma
reimplementação — ver a nota de fidelidade em `app/replay.py`.
"""

from collections import Counter, deque

from app.config import config
from app.main import build_pipeline, process_frame
from app.replay import detections_do_registro
from app.tracker import GameTracker


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(p * len(ordenados)))]


def mede(registros: list[dict], conf_alta: float = 0.80,
         max_exemplos: int = 8) -> dict:
    """Passa a partida gravada pelo pipeline e devolve os três números.

    `conf_alta` é o limiar da contradição: abaixo dele, uma carta vista e
    ausente da tela é ambígua (pode ser o modelo errando, e aí a tela é que
    está certa). Em 0,80 a leitura é boa o bastante para que a divergência seja
    problema DA TELA — é o mesmo raciocínio do `confirm_confidence`, que ficou
    sem uso quando o evento saiu de escopo.

    Duas decisões de medição que mudam o resultado e não são óbvias:

    1. **Só conta carta que está no LEQUE.** A carta que o jogador segura à
       parte fica visível de propósito fora da tela desde 2026-08-19; cobrá-la
       seria medir o comportamento pedido como defeito. Quem diz o que é leque
       é o próprio leitor (`FanReader.ultimo_leque`), não uma cópia da regra
       aqui — cópia diverge em silêncio. Medido na partida de 19/08: cobrando a
       carta à parte a contradição sobe de 7,5% para 9,2%.

    2. **O atraso é medido a partir da PRIMEIRA vez que a leitura viva mostrou
       aquele conjunto**, e não da última vez que ela mudou. A leitura viva
       pisca: ela vai a B e volta a A, e a versão anterior deste código
       reiniciava o cronômetro a cada piscada — se a tela já mostrava A, o
       atraso saía 0,00 s e entrava na conta. Eram zeros que não correspondiam
       a espera nenhuma e puxavam a mediana para baixo.

    O atraso só é medido nas trocas para uma mão NÃO vazia. Esvaziar a tela é
    governado por outro mecanismo (`fan_expire`, a mão saindo do quadro) e
    misturar os dois mediria duas coisas na mesma média.
    """
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()

    frames = com_imagem = com_mao = com_carta = com_carta_e_mao = 0
    duracao = 0.0
    atrasos: list[float] = []
    trocas = 0
    sem_leitura_viva = 0
    visto_desde: dict[tuple, float] = {}
    # começa em "tela vazia", que é o estado real antes do primeiro frame —
    # inicializar em None contaria a partida inteira como tendo uma troca a
    # mais, e `trocas` é justamente o número que denuncia tremor
    exibida_antes: tuple = ()

    ordem_ok = ordem_ruim = 0
    exemplos_ordem: list[tuple] = []

    contradiz = 0
    por_carta: Counter = Counter()
    exemplos_contra: list[tuple] = []

    # Janela do EXCESSO: quantas vezes cada código apareceu no quadro em cada um
    # dos últimos frames. O teto é o MÁXIMO da janela, não o do frame atual —
    # senão uma carta momentaneamente encoberta (o dedo passando) contaria como
    # sobrando, e ficar exibindo a carta durante a oclusão é o comportamento
    # certo, não defeito.
    janela: deque = deque(maxlen=max(config.fan_window, 1))
    excesso = 0
    por_carta_excesso: Counter = Counter()
    exemplos_excesso: list[tuple] = []

    for rec in registros:
        if rec["t"] != "frame":
            continue
        frames += 1
        if rec.get("v", -1) >= 0:
            com_imagem += 1
        ts = rec.get("ts", 0.0)
        duracao = max(duracao, ts)

        dets = detections_do_registro(rec, config.min_confidence)
        if dets:
            com_carta += 1
        process_frame(dets, tracker, leitor, trava, verbose=False)
        leque = leitor.ultimo_leque
        # entra ANTES de medir o excesso: a carta que acabou de aparecer no
        # quadro não pode ser cobrada como sobrando na tela
        janela.append(Counter(d.card.code for d in leque))

        vivo = tuple(sorted(leitor.cards))
        visto_desde.setdefault(vivo, ts)

        exibida = trava.cards
        chave = tuple(sorted(exibida))
        if chave != exibida_antes:
            trocas += 1
            if exibida:
                inicio = visto_desde.get(chave)
                if inicio is None:
                    # a tela mostrou um conjunto que a leitura viva nunca
                    # mostrou inteiro. Acontece porque o StableHand soma
                    # presença ao longo do tempo: a mão exibida é uma UNIÃO de
                    # frames. Não é atraso, é outra coisa — contar como zero
                    # esconderia; fica em contagem própria.
                    sem_leitura_viva += 1
                else:
                    atrasos.append(ts - inicio)
            visto_desde = {vivo: ts}
            exibida_antes = chave

        if not exibida:
            continue
        com_mao += 1
        # numerador da cobertura: os dois ao mesmo tempo. Sem exigir a carta no
        # quadro, o rastro que a tela mantém depois de as cartas saírem (a mão
        # só some depois de `fan_expire`) fazia a cobertura passar de 100%
        if dets:
            com_carta_e_mao += 1

        # ORDEM: só faz sentido comparar quando a tela tem as MESMAS cartas do
        # quadro. Quando as cartas divergem, o que existe é erro de conjunto,
        # que já é cobrado pela contradição — cobrar de novo aqui contaria o
        # mesmo defeito duas vezes.
        fisica = [d.card.code
                  for d in sorted(leque, key=lambda d: (d.box[0] + d.box[2]) / 2)]
        if Counter(fisica) == Counter(exibida):
            if fisica == list(exibida):
                ordem_ok += 1
            else:
                ordem_ruim += 1
                if len(exemplos_ordem) < max_exemplos:
                    exemplos_ordem.append((rec["i"], round(ts, 1),
                                           list(exibida), fisica))

        # EXCESSO: a tela mostra mais cópias de um código do que o quadro
        # chegou a mostrar de uma vez na janela recente. Pega tanto a carta que
        # some do quadro e fica na tela quanto a vaga órfã que duplica a mesma
        # carta — foi assim que a mão exibida chegou a 17 cartas em 20/08.
        teto: Counter = Counter()
        for c in janela:
            for code, n in c.items():
                if n > teto[code]:
                    teto[code] = n
        sobrando = Counter(exibida) - teto
        if sobrando and janela:
            excesso += 1
            for code in sobrando:
                por_carta_excesso[code] += 1
            if len(exemplos_excesso) < max_exemplos:
                exemplos_excesso.append((rec["i"], round(ts, 1),
                                         " ".join(sorted(sobrando.elements())),
                                         list(exibida)))

        vistas = Counter(d.card.code for d in leque
                         if d.confidence >= conf_alta)
        sobra = vistas - Counter(exibida)
        if sobra:
            contradiz += 1
            for code in sobra:
                por_carta[code] += 1
            if len(exemplos_contra) < max_exemplos:
                exemplos_contra.append((rec["i"], round(ts, 1),
                                        " ".join(sorted(sobra.elements())),
                                        list(exibida)))

    uteis = com_imagem or frames
    comparaveis = ordem_ok + ordem_ruim
    return {
        "frames": frames,
        "com_imagem": com_imagem,
        "com_mao": com_mao,
        "com_carta": com_carta,
        "duracao": duracao,
        "fps": uteis / duracao if duracao else 0.0,
        # denominador = frames com carta no quadro, NÃO frames da gravação:
        # a gravação inclui o tempo em que ninguém estava na frente da câmera,
        # e medir contra ela transforma "app ligado sozinho" em defeito de
        # enquadramento. Foi o erro cometido em 2026-08-20.
        "com_carta_e_mao": com_carta_e_mao,
        "cobertura": com_carta_e_mao / com_carta if com_carta else 0.0,
        "atividade": com_carta / frames if frames else 0.0,
        "atraso": {
            "n": len(atrasos),
            "mediana": _percentil(atrasos, 0.5),
            "p90": _percentil(atrasos, 0.9),
            "max": max(atrasos) if atrasos else 0.0,
            "sem_leitura_viva": sem_leitura_viva,
        },
        "trocas": trocas,
        "ordem": {
            "comparaveis": comparaveis,
            "errada": ordem_ruim,
            "pct": ordem_ruim / comparaveis if comparaveis else 0.0,
            "exemplos": exemplos_ordem,
        },
        "contradicao": {
            "frames": contradiz,
            "pct": contradiz / com_mao if com_mao else 0.0,
            "conf": conf_alta,
            "por_carta": por_carta.most_common(),
            "exemplos": exemplos_contra,
        },
        "excesso": {
            "frames": excesso,
            "pct": excesso / com_mao if com_mao else 0.0,
            "por_carta": por_carta_excesso.most_common(),
            "exemplos": exemplos_excesso,
        },
    }


def imprime(res: dict, rotulo: str = "", detalhar: bool = True):
    """Uma linha por número, sem caractere fora do cp1252.

    O terminal do Windows quebra a saída INTEIRA num UnicodeEncodeError quando
    o stdout é redirecionado — e medição que só funciona na tela não serve para
    guardar em arquivo.
    """
    print(f"--- {rotulo}" if rotulo else "---")
    if res["fps"]:
        # o FPS não é vaidade: todos os parâmetros do pipeline são contados em
        # FRAMES, e é ele que converte `lock_frames` para segundos
        print(f"  {res['com_imagem'] or res['frames']} frames em "
              f"{res['duracao']:.0f}s = {res['fps']:.1f} fps | "
              f"lock_frames={config.lock_frames} ~ "
              f"{config.lock_frames / res['fps']:.1f}s")
    a = res["atraso"]
    print(f"  ATRASO ate a tela: mediana {a['mediana']:.2f}s | "
          f"p90 {a['p90']:.2f}s | max {a['max']:.2f}s  (n={a['n']})")
    if a["sem_leitura_viva"]:
        print(f"    +{a['sem_leitura_viva']} trocas para um conjunto que a "
              f"leitura viva nunca mostrou inteiro (uniao no tempo)")
    c = res["contradicao"]
    print(f"  CONTRADICAO: {c['frames']}/{res['com_mao']} frames "
          f"({100 * c['pct']:.1f}%) com carta no leque a conf >= {c['conf']} "
          f"fora da tela")
    e = res["excesso"]
    print(f"  EXCESSO: {e['frames']}/{res['com_mao']} frames "
          f"({100 * e['pct']:.1f}%) com carta na tela que o quadro nao mostrou")
    o = res["ordem"]
    print(f"  ORDEM errada: {o['errada']}/{o['comparaveis']} frames "
          f"({100 * o['pct']:.1f}%)")
    print(f"  TROCAS da mao exibida: {res['trocas']}")
    print(f"  COBERTURA: mao na tela em {res['com_carta_e_mao']}/"
          f"{res['com_carta']} frames COM CARTA no quadro "
          f"({100 * res['cobertura']:.1f}%)")
    print(f"  ATIVIDADE: carta no quadro em {res['com_carta']}/{res['frames']} "
          f"frames da gravacao ({100 * res['atividade']:.1f}%)")
    if not detalhar:
        return
    if c["por_carta"]:
        print("  cartas vistas e ausentes da tela (frames):")
        for code, n in c["por_carta"][:10]:
            print(f"    {code:4s} {n:5d}")
    for i, ts, sobra, exib in c["exemplos"][:5]:
        print(f"    i={i:6d} t={ts:7.1f}s  fora da tela: {sobra:12s} | "
              f"tela: {' '.join(exib)}")
    for i, ts, exib, fis in o["exemplos"][:3]:
        print(f"    i={i:6d} t={ts:7.1f}s  ordem")
        print(f"      tela: {' '.join(exib)}")
        print(f"      real: {' '.join(fis)}")
