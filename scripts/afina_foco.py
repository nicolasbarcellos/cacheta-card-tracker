"""Acha o FOCO fixo da câmera da mão, medindo o leque de verdade.

## Por que existe

O foco ficou no automático desde o começo do projeto, e ninguém olhou. Em
2026-09-18, no estúdio, a câmera abriu com o foco em **14** e a gravação saiu
com nitidez **2.679** no leque PARADO — contra 4.579 da gravação de 16/09 e
~4.000 medidos aqui no foco certo. E não era luz: brilho 185 dentro do índice,
0,7% de pixel estourado.

O mecanismo é geométrico, não da câmera: **o autofoco mira o que PREENCHE o
quadro**. Com a câmera sobre a mesa, o que preenche é o feltro — e o leque fica
mais perto, fora daquele plano. Quanto mais a mesa domina o quadro, pior.

Borrão com o objeto PARADO não é exposição nem movimento; é foco. Esse é o
sinal que manda rodar isto aqui.

## Como usar

Com o app FECHADO (duas instâncias não abrem a mesma câmera), segure o leque
aberto **na posição em que joga** e parado:

    python scripts/afina_foco.py                 # varredura grossa, 0..255
    python scripts/afina_foco.py 80,85,90,95,100 # afina em volta do pico

Ponha o valor escolhido em `config.cam_foco` (0 devolve ao automático).

## Como ler o resultado

A coluna que decide é a **nitidez** (Laplaciano dentro do retângulo do leque,
com o quadro reduzido a 1280, que é como o modelo o vê — medir no quadro cru
mede o resize). Ela tem pico estreito: medido em 18/09, 501 no foco 0, 1.138 no
30, ~4.000 entre 85 e 105, 97 no 255. Escolha o MEIO do platô.

**Não decida pela contagem de cartas.** Medido no mesmo dia: num A/B de
autofoco × foco fixo, quem rodava PRIMEIRO ganhava nos dois sentidos — com o
leque na mão, ele baixa alguns milímetros a cada dezena de segundos e isso
mexe mais na contagem do que o foco. A contagem fica na tabela como sinal
grosseiro; a nitidez é a medida.

O valor é da DISTÂNCIA, não do produto: reafira ao mudar a câmera de lugar, a
altura da mesa ou a webcam.
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config          # noqa: E402
from app.detector import CardDetector  # noqa: E402

GROSSA = [0, 15, 30, 45, 60, 75, 90, 105, 120, 150, 180, 210, 255]
ASSENTA = 1.2      # segundos para a lente andar antes de medir
DESCARTA = 4       # quadros presos no buffer do driver
AMOSTRAS = 4


def nitidez_do_leque(img, dets) -> float:
    """Laplaciano dentro do retângulo do leque, com o quadro a 1280.

    Reduzir antes é o que faz a medida ser a do MODELO: no quadro cru de 1080p
    o que se mede é o detalhe que o resize vai jogar fora.
    """
    xs = [c for d in dets for c in (d.box[0], d.box[2])]
    ys = [c for d in dets for c in (d.box[1], d.box[3])]
    k = 1280 / img.shape[1]
    peq = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    rec = peq[max(0, int(min(ys) * k)):int(max(ys) * k),
              max(0, int(min(xs) * k)):int(max(xs) * k)]
    if rec.size < 1000:
        return 0.0
    return float(cv2.Laplacian(cv2.cvtColor(rec, cv2.COLOR_BGR2GRAY),
                               cv2.CV_64F).var())


def main():
    valores = ([int(v) for v in sys.argv[1].split(",")]
               if len(sys.argv) > 1 else GROSSA)
    det = CardDetector(config.model_path, config.min_confidence,
                       imgsz=config.detect_imgsz,
                       agnostic_nms=config.agnostic_nms)
    cap = cv2.VideoCapture(config.hand_cam_index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
    if not cap.read()[0]:
        print("a câmera não entregou quadro — o app está aberto?")
        return

    print("segure o leque PARADO, na posição de jogo\n")
    print(f"{'foco':>6} {'NITIDEZ':>9} {'cartas':>7} {'conf p50':>9}")
    tabela = []
    for f in valores:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        cap.set(cv2.CAP_PROP_FOCUS, f)
        time.sleep(ASSENTA)
        for _ in range(DESCARTA):
            cap.read()
        linhas = []
        for _ in range(AMOSTRAS):
            ok, img = cap.read()
            if not ok:
                continue
            dets = det.detect(img)
            if not dets:
                linhas.append((0.0, 0, 0.0))
                continue
            linhas.append((nitidez_do_leque(img, dets), len(dets),
                           float(np.median([d.confidence for d in dets]))))
        if not linhas:
            continue
        a = np.array(linhas)
        tabela.append((f, a[:, 0].mean(), a[:, 1].mean(), np.median(a[:, 2])))
        print(f"{f:6d} {tabela[-1][1]:9.0f} {tabela[-1][2]:7.2f} "
              f"{tabela[-1][3]:9.2f}")
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)      # devolve a câmera ao automático
    cap.release()

    if tabela:
        pico = max(tabela, key=lambda r: r[1])
        plato = [r[0] for r in tabela if r[1] >= 0.9 * pico[1]]
        print(f"\npico em {pico[0]} (nitidez {pico[1]:.0f})")
        print(f"platô (>=90% do pico): {plato} -> "
              f"config.cam_foco = {plato[len(plato) // 2]}")


if __name__ == "__main__":
    main()
