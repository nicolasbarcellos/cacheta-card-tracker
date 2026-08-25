"""Ensina o modelo a carta que ele PERDE — os frames em que a conta quase fecha.

O `extrai_gravacao.py` só aceita frame em que a contagem BATE (`alinhado`), e
com razão: uma carta não detectada desloca todos os rótulos seguintes. O efeito
colateral é que **todo frame em que o modelo perdeu uma carta é descartado
inteiro** — justamente os frames que carregam o dado difícil. Medido em
2026-08-24: a carta some por **1,6 s (mediana) a 5 s** com a mão inteira no
quadro, 60-88% das vezes numa PONTA do leque, sempre precedida de confiança já
degradada (p10 0,34-0,47 contra 0,82-0,88 da base). E medido em 2026-08-25:
64-89% de tudo o que a tela mostra e o leque não tem é isto — o modelo não
entregou a carta.

## Onde está a verdade, já que aqui não há gabarito

Não precisa de gabarito, e é o que faz este script rodar nas quatro gravações
que ainda têm vídeo (as duas com gabarito são 11/08 — que é o conjunto de
validação real, e tem de ficar fora do treino — e 12/08, cujo `mao.avi` já não
existe).

Quem diz que carta é aquela é o **próprio leitor**: a vaga do `FanReader` que
ficou sem detecção neste frame já tem rótulo estabelecido pela votação
ponderada dos frames em que a carta FOI vista, e posição atualizada pela
compensação de movimento (`_estimate_shift`) mesmo nos frames em que ela não
apareceu. É a mesma decisão de sempre neste repositório — quem diz o que é
leque é o leitor, não uma cópia da regra aqui, que divergiria em silêncio.

Isso NÃO é a circularidade do `auto_annotate.py`. Lá o rótulo saía do palpite
do modelo NAQUELE frame, então a carta que ele erra nunca aprende. Aqui o
defeito que se conserta é PERDA DE DETECÇÃO, não erro de classe: o rótulo vem
dos frames vizinhos, em que a mesma carta foi lida forte, e o frame difícil é
aquele em que ela sumiu.

## A guarda que decide tudo: 69% dos buracos são oclusão FÍSICA

Medido em 2026-08-24 re-detectando os buracos do vídeo: em 69% deles a carta não
aparece **nem baixando o limiar a 0,05** — é dedo na frente, ou carta atrás de
carta. Rotular esses seria ensinar o modelo a enxergar índice que não está na
imagem, que é o envenenamento oposto ao que o `extrai_negativos.py` evita e o
mesmo que reprovou o `extrai_fantasmas.py` duas vezes na auditoria.

Por isso a caixa NÃO é interpolada. O frame é re-detectado a 0,05 e só entra se
o modelo responder ALGUMA COISA na posição que a vaga previu: aí o índice está
visível (o modelo reagiu a ele), a caixa é real e o que faltava era confiança ou
classe. Se não responder nada, o buraco é oclusão e o frame é descartado — e
contado, que é como se sabe a proporção.

## As outras guardas

- **uma vaga só perdida**: duas cartas sumindo ao mesmo tempo é o leque
  fechando ou a mão passando na frente, não perda de detecção;
- **leitor não congelado**: oclusão declarada pelo próprio leitor;
- **buraco recente** (`MAX_MISSES`): quanto mais velho, menos a posição prevista
  vale;
- **código único na mão exibida**: com duas cartas do mesmo código não dá para
  saber qual vaga é qual, e vaga órfã de leque que se moveu duplica código;
- **todas as outras vagas casadas** na re-detecção: se uma detecção forte do
  vídeo não corresponde a vaga nenhuma (carta na mesa, canto invertido), o
  arquivo de rótulo deixaria região visível SEM rótulo — que é o que ensina o
  modelo a chamar índice de fundo;
- **tamanho compatível** com as vizinhas: uma fresta de carta atrás de carta
  responde a 0,05 numa caixa muito menor, e rotular fresta é ensinar o glifo
  errado;
- **tinta no glifo**: a metade de CIMA da caixa (onde mora o glifo; o pip fica
  embaixo) precisa ter tinta comparável à das vizinhas do mesmo frame. Pega a
  carta que a luz estourou — medido nos 31 primeiros recortes de 20/08: 0,27,
  0,33 e 0,27 contra 0,80 do próximo, um vão limpo, e os três eram ilegíveis na
  auditoria. É relativa às vizinhas de propósito: limiar absoluto de brilho
  dependeria da iluminação da sessão.

E a última guarda é o OLHO, e ela não é dispensável — a auditoria da primeira
rodada reprovou 7 dos 31 recortes. `contato.jpg` traz cada carta recuperada com
o entorno e a caixa marcada; apagar a imagem de `review/` rejeita o frame, que é
o mesmo mecanismo do `extrai_gravacao.py` e o que o `finetune_local.py` respeita.

## Duas guardas automáticas MEDIDAS E REFUTADAS (não reimplemente)

O que sobra depois da tinta é sempre a mesma coisa: a caixa contém **pip sem
glifo** — dedo por cima, carta vizinha cobrindo, ou a caixa caiu no meio da
carta (num diamante, dois pips seguidos parecem índice). Duas tentativas de
separar isso por medida, ambas nos 31 recortes auditados:

- **perguntar ao modelo com o recorte AMPLIADO** ("se há índice aqui, ele o lê
  com folga a 4×"). Não funciona porque **o modelo é preso à escala**: em 28 dos
  31 recortes ampliados ele não detectou NADA, incluindo os que a auditoria
  aprovou. Ampliar tira o índice da escala em que ele foi treinado.
- **fração de PELE na metade do glifo** (dedo cobrindo). Não separa: os recortes
  APROVADOS tinham 0,50-0,67 de pele contra 0,26-0,55 dos reprovados — o dedo
  aparece nos dois, e a régua ainda acende no amarelado do verso da carta.

O sinal que a auditoria usa é "vejo o glifo?", e ele não foi reduzido a número.

Uso:
    python training/extrai_dificeis.py gravacoes/20260820-194355 --so-analise
    python training/extrai_dificeis.py gravacoes/20260820-194355
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import config  # noqa: E402
from app.detector import hand_instances  # noqa: E402
from app.main import build_pipeline, process_frame  # noqa: E402
from app.replay import carrega, detections_do_registro  # noqa: E402
from app.tracker import GameTracker  # noqa: E402

ROOT = Path(__file__).resolve().parent

# Frames desde a perda. O buraco dura 1,6-5 s, mas a posição prevista pela vaga
# envelhece: ela acompanha a translação GLOBAL do leque, não o movimento da
# carta dentro dele. 12 frames (~0,4 s) é o quanto a compensação de movimento
# cobre com folga — e frame descartado aqui é barato, sobram buracos.
MAX_MISSES = 12
MIN_VAGAS = 4          # menos que isto não é leque, é resto de leitura
POR_CARTA = 6          # teto de amostras do mesmo código — ver `acha_candidatos`
CONF_BAIXA = 0.05      # limiar da re-detecção: "o modelo reagiu a alguma coisa?"
CONF_FORTE = 0.30      # o limiar do app: detecção que TEM de casar com vaga
TAM_MIN, TAM_MAX = 0.55, 1.7   # tamanho da caixa recuperada / mediana das outras
TINTA_MIN = 0.5        # tinta no glifo / mediana das vizinhas — ver a docstring
LADO_CONTATO = 230     # px por recorte na folha de contato
MARGEM_CONTATO = 45    # px de entorno no recorte: sem contexto não se audita


def _centro(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def tinta_glifo(frame, box) -> float:
    """Fração de pixels escuros na metade de CIMA da caixa (onde fica o glifo).

    O pip fica embaixo e sobrevive ao estouro de luz; o glifo, não. O corte é
    relativo ao próprio recorte (p90 da luminância) para não depender da
    iluminação — e o resultado só é usado contra a mediana das vizinhas DO
    MESMO frame, que é a única comparação justa.
    """
    import numpy as np
    x1, y1, x2, y2 = (int(v) for v in box)
    rec = frame[max(0, y1):max(y2, y1 + 1), max(0, x1):max(x2, x1 + 1)]
    if rec.size == 0:
        return 0.0
    topo = rec[:max(1, int(0.55 * rec.shape[0]))]
    g = cv2.cvtColor(topo, cv2.COLOR_BGR2GRAY).astype("float32")
    claro = float(np.percentile(g, 90))
    if claro <= 1:
        return 0.0
    return float((g < 0.62 * claro).mean())


def acha_candidatos(registros, intervalo, max_misses, max_por_carta):
    """Frames em que UMA vaga do leitor ficou sem detecção. Não abre o vídeo.

    Devolve (candidatos, buracos, perda), onde cada candidato traz a vaga perdida
    e o retrato das outras vagas naquele instante — é com ele que a re-detecção
    confere se o vídeo mostra o mesmo leque que a sessão gravada mostrou.

    `perda` é a TAXA DE PERDA DE DETECÇÃO: das vagas já estabelecidas, quantas
    ficam sem detecção no frame. É a nota do alvo, e vale para ela o mesmo que
    para a nota da tela: com `--dets`, comparar dois modelos no MESMO vídeo.

    **Não use a contagem de BURACOS para isso**, e a razão é medida: ela exige
    EXATAMENTE uma vaga perdida, então melhorar as outras vagas faz o contador
    SUBIR. Comparando o modelo de 20/08 com o de 25/08 nas duas gravações fora
    do treino, os buracos foram 190→202 numa e 197→167 na outra — direções
    opostas — enquanto a taxa de perda caiu nas duas (5,69%→4,97% e
    4,20%→3,98%). O contador serve para dimensionar o rendimento da extração,
    não para dizer se o modelo melhorou.
    """
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()
    candidatos = []
    buracos = Counter()
    por_carta: Counter = Counter()
    vagas_tot = vagas_perdidas = 0
    ultimo = -9e9
    for rec in registros:
        if rec.get("t") != "frame":
            continue
        dets = detections_do_registro(rec, config.min_confidence)
        process_frame(dets, tracker, leitor, trava, verbose=False)
        if leitor.congelado or rec.get("v", -1) < 0:
            continue
        vagas = [v for v in leitor.slots_debug()
                 if v["n"] >= config.fan_min_appear and v["label"]]
        if len(vagas) < MIN_VAGAS:
            continue
        perdidas = [v for v in vagas if v["misses"] >= 1]
        vagas_tot += len(vagas)
        vagas_perdidas += len(perdidas)
        if len(perdidas) != 1:
            continue
        perdida = perdidas[0]
        if perdida["misses"] == 1:
            buracos[perdida["label"]] += 1   # primeiro frame = um buraco novo
        if perdida["misses"] > max_misses:
            continue
        exibida = Counter(c.code for c in tracker.hand_view)
        if exibida.get(perdida["label"]) != 1:
            continue        # código repetido: não dá para saber qual vaga é qual
        if Counter(v["label"] for v in vagas)[perdida["label"]] != 1:
            continue
        if rec["ts"] - ultimo < intervalo:
            continue
        # TETO POR CARTA. Com a mão parada, uma carta que fica minutos sem ser
        # detectada rende dezenas de frames quase idênticos: na primeira
        # extração de 19/08 15:50, 9 dos 21 recortes eram o MESMO J♥ na mesma
        # pose. Não é dado novo, e o `finetune_local.py` ainda repete o real
        # para ele pesar ~30% do treino — a repetição seria multiplicada.
        if por_carta[perdida["label"]] >= max_por_carta:
            continue
        por_carta[perdida["label"]] += 1
        ultimo = rec["ts"]
        candidatos.append({
            "v": rec["v"], "ts": rec["ts"], "misses": perdida["misses"],
            "perdida": (perdida["x"], perdida["y"], perdida["label"]),
            "vagas": [(v["x"], v["y"], v["label"]) for v in vagas],
        })
    return candidatos, buracos, (vagas_perdidas, vagas_tot)


def casa_vagas(dets, vagas, match_dist):
    """Casa detecção→vaga pela proximidade. Devolve None se sobrar alguma.

    "Sobrar" é o caso perigoso: detecção forte que não corresponde a vaga
    nenhuma é carta na mesa ou canto invertido, e ela ficaria no frame SEM
    rótulo — ensinando o modelo que aquele padrão é fundo.
    """
    casado: dict[int, object] = {}
    for d in dets:
        cx, cy = _centro(d.box)
        melhor, melhor_dist = None, match_dist
        for i, (x, y, _label) in enumerate(vagas):
            dist = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
            if dist < melhor_dist:
                melhor, melhor_dist = i, dist
        if melhor is None or melhor in casado:
            return None
        casado[melhor] = d
    return casado


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--intervalo", type=float, default=0.5,
                    help="segundos entre amostras (frames vizinhos são iguais)")
    ap.add_argument("--max-misses", type=int, default=MAX_MISSES)
    ap.add_argument("--por-carta", type=int, default=POR_CARTA,
                    help="teto de amostras do mesmo codigo (mao parada repete)")
    ap.add_argument("--max", type=int, default=400,
                    help="teto de frames re-detectados")
    ap.add_argument("--so-analise", action="store_true",
                    help="conta os candidatos sem abrir o vídeo")
    ap.add_argument("--modelo", default=config.model_path)
    ap.add_argument("--dets", type=Path,
                    help="outro arquivo de deteccoes (ex.: de --redetectar). "
                         "Com --so-analise, e como se compara quantos BURACOS "
                         "dois modelos abrem no MESMO video")
    args = ap.parse_args()

    origem = args.gravacao / "sessao.jsonl"
    if args.dets:
        origem = args.dets if args.dets.exists() else args.gravacao / args.dets
    registros = carrega(origem)
    candidatos, buracos, perda = acha_candidatos(
        registros, args.intervalo, args.max_misses, args.por_carta)
    perdidas, vagas = perda
    print(f"{args.gravacao.name}: PERDA DE DETECCAO {perdidas}/{vagas} vagas "
          f"estabelecidas = {100 * perdidas / max(vagas, 1):.2f}%")
    print(f"  {sum(buracos.values())} buracos (uma vaga sozinha perdendo), "
          f"{len(candidatos)} frames candidatos "
          f"-- a contagem de buracos NAO mede modelo, ver acha_candidatos")
    for code, n in buracos.most_common(10):
        print(f"  {code}: {n} buracos")
    if args.so_analise or not candidatos:
        return
    if len(candidatos) > args.max:
        passo = len(candidatos) / args.max
        candidatos = [candidatos[int(k * passo)] for k in range(args.max)]
        print(f"  amostrados {len(candidatos)} (teto --max)")

    video = args.gravacao / "mao.avi"
    if not video.exists():
        raise SystemExit(f"sem video em {video} — esta gravacao nao serve")

    from app.detector import CardDetector  # import tardio: puxa o torch
    detector = CardDetector(args.modelo, CONF_BAIXA, imgsz=config.detect_imgsz)
    from ultralytics import YOLO  # noqa: E402
    nomes = YOLO(args.modelo).names
    name_to_id = {nome: i for i, nome in nomes.items()}

    # sai em datasets/real/, e não numa pasta nova: é dado real da mesma
    # natureza (imagem real, rótulo vindo da posição/votação, revisão por
    # review/), e assim o `finetune_local.py` o consome sem mudar uma linha —
    # com a repetição do real e o `--holdout` por nome de pasta.
    dst = args.saida or (ROOT / "datasets" / "real"
                         / f"{args.gravacao.name}-dificeis")
    for sub in ("images", "labels", "review"):
        (dst / sub).mkdir(parents=True, exist_ok=True)

    motivos: Counter = Counter()
    recuperadas: Counter = Counter()
    recortes = []
    salvos = 0
    cap = cv2.VideoCapture(str(video))
    v = 0
    for c in candidatos:
        while v < c["v"]:
            if not cap.grab():
                break
            v += 1
        ok, frame = cap.read()
        if not ok:
            break
        v += 1
        h, w = frame.shape[:2]
        brutas = detector.detect(frame)
        fortes = hand_instances([d for d in brutas if d.confidence >= CONF_FORTE])
        px, py, label = c["perdida"]

        casado = casa_vagas(fortes, c["vagas"], config.fan_match_dist)
        if casado is None:
            motivos["deteccao forte sem vaga (carta na mesa?)"] += 1
            continue
        perdida_i = next(i for i, (_x, _y, lb) in enumerate(c["vagas"])
                         if lb == label)
        if perdida_i in casado:
            motivos["o video detectou a carta (MJPG != ao vivo)"] += 1
            continue
        if len(casado) != len(c["vagas"]) - 1:
            motivos["vaga sem deteccao alem da perdida"] += 1
            continue

        # a carta reapareceu a 0,05? é o que separa "o modelo hesitou" de
        # "a carta não está na imagem"
        perto = [d for d in hand_instances(brutas)
                 if ((_centro(d.box)[0] - px) ** 2
                     + (_centro(d.box)[1] - py) ** 2) ** 0.5
                 < config.fan_match_dist
                 and d.confidence < CONF_FORTE]
        if not perto:
            motivos["OCLUSAO: nada na posicao nem a 0,05"] += 1
            continue
        achada = max(perto, key=lambda d: d.confidence)

        alturas = sorted(d.box[3] - d.box[1] for d in casado.values())
        hmed = alturas[len(alturas) // 2]
        alt = achada.box[3] - achada.box[1]
        if not (TAM_MIN * hmed <= alt <= TAM_MAX * hmed):
            motivos["caixa de tamanho incompativel (fresta?)"] += 1
            continue

        tintas = sorted(tinta_glifo(frame, d.box) for d in casado.values())
        tmed = tintas[len(tintas) // 2]
        if tmed > 0 and tinta_glifo(frame, achada.box) < TINTA_MIN * tmed:
            motivos["glifo sem tinta (luz estourada?)"] += 1
            continue

        linhas, view = [], frame.copy()
        for i, d in casado.items():
            code = c["vagas"][i][2]
            x1, y1, x2, y2 = (int(b) for b in d.box)
            linhas.append(f"{name_to_id[code]} {(x1 + x2) / 2 / w:.6f} "
                          f"{(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} "
                          f"{(y2 - y1) / h:.6f}")
            cv2.rectangle(view, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(view, code, (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0), 2)
        x1, y1, x2, y2 = (int(b) for b in achada.box)
        linhas.append(f"{name_to_id[label]} {(x1 + x2) / 2 / w:.6f} "
                      f"{(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} "
                      f"{(y2 - y1) / h:.6f}")
        cv2.rectangle(view, (x1, y1), (x2, y2), (255, 0, 255), 3)
        cv2.putText(view, f"{label} <- {achada.card.code} {achada.confidence:.2f}",
                    (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)

        nome = f"{args.gravacao.name}_{c['v']:06d}"
        cv2.imwrite(str(dst / "images" / f"{nome}.jpg"), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        (dst / "labels" / f"{nome}.txt").write_text("\n".join(linhas))
        cv2.imwrite(str(dst / "review" / f"{nome}.jpg"), view,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])
        recuperadas[f"{label} (modelo via {achada.card.code} "
                    f"{achada.confidence:.2f})"] += 1
        m = MARGEM_CONTATO
        rx1, ry1 = max(0, x1 - m), max(0, y1 - m)
        recorte = frame[ry1:min(h, y2 + m), rx1:min(w, x2 + m)].copy()
        if recorte.size:
            # a caixa exata marcada DENTRO do recorte: sem ela não dá para
            # saber se o glifo que se está lendo é o da carta certa ou o da
            # vizinha que entrou no entorno
            cv2.rectangle(recorte, (x1 - rx1, y1 - ry1),
                          (x2 - rx1, y2 - ry1), (255, 0, 255), 2)
            recortes.append((nome, label, achada, recorte))
        salvos += 1
        if salvos % 25 == 0:
            print(f"  {salvos} salvos", flush=True)
    cap.release()

    print(f"\n{salvos} frames com carta RECUPERADA salvos em {dst}")
    total = salvos + sum(motivos.values())
    for motivo, n in motivos.most_common():
        print(f"  descartados por {motivo}: {n} ({100 * n / max(total, 1):.0f}%)")
    print("\ncartas recuperadas:")
    for k, n in recuperadas.most_common(20):
        print(f"  {n:4d}x  {k}")

    if recortes:
        folha = contato(recortes)
        cv2.imwrite(str(dst / "contato.jpg"), folha,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"\nfolha de contato: {dst / 'contato.jpg'} — OLHE antes de treinar")
    (dst / "dificeis.json").write_text(json.dumps(
        {n: {"rotulo": lb, "modelo_viu": a.card.code,
             "confianca": round(a.confidence, 3)}
         for n, lb, a, _r in recortes}, indent=2), encoding="utf-8")


def contato(recortes, por_linha=6):
    """Folha de contato dos recortes recuperados, com ENTORNO e sem distorcer.

    Três decisões que a primeira auditoria mostrou serem necessárias, todas
    olhando as mesmas 31 imagens:

    - **entorno** (`MARGEM_CONTATO`): sem as cartas vizinhas não se distingue
      "o glifo está coberto" de "o glifo está fora do recorte";
    - **proporção preservada**: o índice é estreito e alto; esticá-lo para um
      quadrado deforma justamente o glifo que se quer ler;
    - **a caixa marcada** dentro do recorte, senão lê-se o glifo da vizinha e
      aprova-se um rótulo errado.

    O número de cada quadro é o índice em `dificeis.json`, para a rejeição ser
    rastreável até o arquivo que precisa ser apagado de `review/`.
    """
    import numpy as np
    L = LADO_CONTATO
    linhas = (len(recortes) + por_linha - 1) // por_linha
    folha = np.zeros((linhas * (L + 24), por_linha * L, 3), dtype="uint8")
    for k, (_nome, label, achada, recorte) in enumerate(recortes):
        lin, col = divmod(k, por_linha)
        alt, larg = recorte.shape[:2]
        esc = min(L / larg, L / alt)
        alvo = cv2.resize(recorte, (int(larg * esc), int(alt * esc)))
        y0, x0 = lin * (L + 24), col * L
        folha[y0:y0 + alvo.shape[0], x0:x0 + alvo.shape[1]] = alvo
        cv2.putText(folha, f"{k}: {label} <- {achada.card.code} "
                    f"{achada.confidence:.2f}", (x0 + 3, y0 + L + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return folha


if __name__ == "__main__":
    main()
