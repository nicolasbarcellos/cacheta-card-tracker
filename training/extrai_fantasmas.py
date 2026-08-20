"""Ensina o modelo a NÃO ver a carta que ele inventa em cima de outra carta.

Medido em 2026-08-20, na partida `20260820-174248`: o **canto invertido** de uma
carta vira outra carta. O 9♠ tem o índice de baixo impresso de cabeça para
baixo, e um **9 girado 180° é visualmente um 6** — o modelo lê ali um `6S` com
**0,93 de confiança**, numa mão que não tinha nenhum 6. Foram 4.378 frames,
entre t=42 s e t=139 s.

É diferente do fantasma de AMBIENTE (`extrai_negativos.py`, o logo da parede):
lá a imagem inteira é fundo e o rótulo é o arquivo vazio. Aqui a imagem TEM
cartas, e o que precisa virar fundo é uma REGIÃO dentro dela — o canto errado
de uma carta que já está contada pelo índice de cima.

O `generate_fans.py` já deixa o canto de baixo sem rótulo, de propósito ("SÓ o
canto de cima é carta"), e mesmo assim o modelo dispara nele. Sintético não
bastou; é o mesmo desfecho do A♠ e do logo, e a saída é a mesma: dado REAL.

A verdade sai da própria gravação, sem gabarito e sem custo de jogo:

    mão EXIBIDA (que o pipeline acertou)  +  detecções do frame
      = as detecções que sobram são o fantasma

O frame só entra se a conta fechar EXATAMENTE — todas as cartas da mão exibida
detectadas, e a sobra composta só de códigos que a mão não tem. Assim o rótulo
não vem do palpite do modelo (ele é conferido contra a mão), e a região do
fantasma fica sem rótulo, que é o que ensina o modelo a ignorá-la.

    python training/extrai_fantasmas.py gravacoes/20260820-174248
    python training/extrai_fantasmas.py gravacoes/... --ate 110 --max 150

STATUS EM 2026-08-20: **a extração foi REPROVADA na auditoria, duas vezes, e
nada dela entrou em treino.** O script fica porque o diagnóstico é útil e o
conserto é identificável — mas não use a saída dele sem resolver o problema
abaixo.

O que a auditoria mostrou, olhando as folhas de contato:

1. Com o limiar do app (0,30), as intrusas são sobretudo leituras FRACAS
   (0,27-0,46) em cima do próprio leque. Daí o `--conf-fantasma`.
2. Com 0,80, as intrusas ficam fortes (0,83-0,94) — mas a MAIORIA continua no
   meio do leque (`7D 0,93`, `KD 0,93`, `3D 0,92`), não no canto invertido.

E aí está o furo do método: uma detecção que sobra pode ser duas coisas
opostas — o canto invertido (que é fundo de verdade) ou **a leitura ERRADA de
uma carta real** cujo índice está exatamente ali. Deixar a segunda sem rótulo
ensina que índice legítimo é fundo, que é o envenenamento que este projeto já
documenta. Confiança não separa as duas.

O que separaria é GEOMETRIA: o canto invertido fica fora da fileira de índices
do leque (é o outro canto de uma carta que já tem índice rotulado), enquanto a
leitura errada cai em cima da fileira. Implementar isso — e auditar de novo — é
o que falta.

RISCO QUE PRECISA SER MEDIDO DEPOIS, e não é pequeno: o canto invertido de um 9
tem os MESMOS PIXELS do índice de um 6 de verdade. Ensinar "isto é fundo" pode
custar detecção de 6 legítimo. O que separa os dois é o contexto (o pip fica
ACIMA do glifo no canto invertido, e abaixo no índice de verdade), e é aposta
que o modelo aprenda isso. Depois do retreino, confira o rank 6 no
`eval_classes.py` contra o holdout de 11/08 — ele tem 150 amostras de 6.

Por isso o `--ate` existe: deixe o fim da janela FORA do treino, para sobrar
com que medir se o fantasma morreu.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config                            # noqa: E402
from app.detector import hand_instances                  # noqa: E402
from app.main import build_pipeline, process_frame       # noqa: E402
from app.replay import carrega, detections_do_registro   # noqa: E402
from app.tracker import GameTracker                      # noqa: E402

RAIZ = Path(__file__).resolve().parent
MIN_MAO = 5           # mão exibida menor que isto não é leque assentado
CONTATO = 12          # miniaturas por folha de contato


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--saida", type=Path, default=RAIZ / "datasets" / "real")
    ap.add_argument("--de", type=float, default=0.0, help="segundo inicial")
    ap.add_argument("--ate", type=float, default=1e9,
                    help="segundo final — deixe o resto FORA para medir depois")
    ap.add_argument("--max", type=int, default=150)
    ap.add_argument("--conf-fantasma", type=float, default=0.80,
                    dest="conf_fantasma",
                    help="confianca minima da INTRUSA. Auditada em 2026-08-20: "
                         "com o limiar do app (0,30) entram sobretudo leituras "
                         "fracas (0,27-0,46) EM CIMA de cartas de verdade, e "
                         "deixa-las sem rotulo ensina que indice legitimo e "
                         "fundo. O canto invertido, que e o alvo, sai a 0,93")
    ap.add_argument("--falta-max", type=int, default=2, dest="falta_max",
                    help="quantas cartas da mao podem faltar no frame")
    ap.add_argument("--passo", type=int, default=12,
                    help="frames mínimos entre duas amostras")
    args = ap.parse_args()

    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()

    candidatos = []
    ultimo = None
    fantasmas: Counter = Counter()
    for rec in carrega(args.gravacao / "sessao.jsonl"):
        if rec["t"] != "frame":
            continue
        dets_brutas = detections_do_registro(rec, config.min_confidence)
        process_frame(dets_brutas, tracker, leitor, trava, verbose=False)
        ts = rec.get("ts", 0.0)
        if not (args.de <= ts <= args.ate) or rec.get("v", -1) < 0:
            continue
        exibida = trava.cards
        if len(exibida) < MIN_MAO:
            continue
        dets = [d for d in hand_instances(dets_brutas)
                if d.confidence >= args.conf_fantasma
                or d.card.code in exibida]
        vistos = Counter(d.card.code for d in dets)
        na_mao = Counter(exibida)
        sobra = vistos - na_mao
        falta = na_mao - vistos
        # Exigir a mão INTEIRA detectada reprovava 3.532 dos 4.962 frames da
        # janela: num leque real sempre há uma carta encoberta pelo dedo ou
        # pela vizinha. O que precisa fechar é a SOBRA (o fantasma), não a
        # presença de todas. Tolerar algumas ausências não estraga rótulo — a
        # carta que não foi detectada simplesmente não vira caixa. O limite
        # existe porque mão muito mal lida é sinal de frame ruim.
        if not sobra or sum(falta.values()) > args.falta_max:
            continue
        # a sobra tem de ser de códigos que a mão NÃO tem — senão não dá para
        # saber qual das duas detecções do mesmo código é a intrusa
        if any(na_mao[code] for code in sobra):
            continue
        if ultimo is not None and rec["i"] - ultimo < args.passo:
            continue
        ultimo = rec["i"]
        reais = [d for d in dets if d.card.code not in sobra]
        candidatos.append((rec, reais, [d for d in dets
                                        if d.card.code in sobra]))
        fantasmas.update(sobra)

    if not candidatos:
        raise SystemExit("nenhum frame com fantasma e mão fechando a conta")
    print(f"{len(candidatos)} frames candidatos entre {args.de:.0f}s e "
          f"{min(args.ate, 1e6):.0f}s")
    print("fantasmas encontrados:", dict(fantasmas.most_common()))

    # amostra espalhada: frames vizinhos são a mesma imagem
    passo = max(1, len(candidatos) // args.max)
    escolhidos = candidatos[::passo][:args.max]

    from ultralytics import YOLO      # import tardio: pesado
    name_to_id = {nome: i for i, nome in YOLO(config.model_path).names.items()}

    dst = args.saida / f"{args.gravacao.name}-fantasma"
    for sub in ("images", "labels", "review"):
        (dst / sub).mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.gravacao / "mao.avi"))
    if not cap.isOpened():
        raise SystemExit(f"não abriu o vídeo em {args.gravacao}")

    miniaturas, salvos = [], 0
    for rec, reais, intrusas in escolhidos:
        cap.set(cv2.CAP_PROP_POS_FRAMES, rec["v"])
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        linhas, view = [], frame.copy()
        for d in reais:
            x1, y1, x2, y2 = (int(b) for b in d.box)
            linhas.append(f"{name_to_id[d.card.code]} "
                          f"{(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                          f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
            cv2.rectangle(view, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(view, d.card.code, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        # o fantasma NÃO vira rótulo — é o ponto do script. Fica marcado em
        # vermelho só na imagem de revisão, para a auditoria conferir que a
        # região é mesmo o canto invertido de uma carta já contada.
        for d in intrusas:
            x1, y1, x2, y2 = (int(b) for b in d.box)
            cv2.rectangle(view, (x1, y1), (x2, y2), (0, 0, 255), 3)
            cv2.putText(view, f"{d.card.code} {d.confidence:.2f} SEM ROTULO",
                        (x1, y2 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255), 2)
        nome = f"{args.gravacao.name}_f{rec['i']:06d}"
        cv2.imwrite(str(dst / "images" / f"{nome}.jpg"), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        (dst / "labels" / f"{nome}.txt").write_text("\n".join(linhas))
        cv2.imwrite(str(dst / "review" / f"{nome}.jpg"), view,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])
        miniaturas.append(cv2.resize(view, (620, 349)))
        salvos += 1
    cap.release()

    for n0 in range(0, len(miniaturas), CONTATO):
        lote = miniaturas[n0:n0 + CONTATO]
        linhas_f = []
        for k in range(0, len(lote), 2):
            fila = lote[k:k + 2]
            while len(fila) < 2:
                fila.append(fila[0] * 0)
            linhas_f.append(cv2.hconcat(fila))
        cv2.imwrite(str(dst / f"contato-{n0 // CONTATO:02d}.jpg"),
                    cv2.vconcat(linhas_f), [cv2.IMWRITE_JPEG_QUALITY, 80])

    print(f"\n{salvos} frames em {dst}")
    print(f"AUDITE {dst}/contato-*.jpg: a caixa VERMELHA tem de ser sempre o "
          f"canto de uma carta que JÁ está rotulada em verde. Se for uma carta "
          f"de verdade, apague a imagem de review/ (o finetune respeita).")


if __name__ == "__main__":
    main()
