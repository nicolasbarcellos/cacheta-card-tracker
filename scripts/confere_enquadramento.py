"""Confere o ENQUADRAMENTO do leque antes de gravar. Não abre janela.

## Por que existe

Custou uma gravação. Em 2026-09-24 gravei 5 min para confirmar o ganho da luz
de 18/09; o foco estava certo e a nitidez foi a melhor já medida no projeto,
mas o leque ficou mais LONGE da câmera e o índice chegou ao modelo com 97 px
em vez de 105-127 px. A perda de detecção saiu 5,53% contra 3,19%, a
comparação não valeu, e o motivo só apareceu depois, na medição.

O irmão deste script é o `afina_foco.py`, e a divisão de trabalho é clara:
aquele acha o foco da DISTÂNCIA; este confere se a distância é a certa.
Rode os dois na ordem — foco primeiro, enquadramento depois — sempre que a
câmera, a mesa ou a cadeira mudarem de lugar.

## Como usar

Com o app FECHADO (dois processos não abrem a mesma câmera — em 18/09 isso
zerou um `mao.avi` e travou o app), segure o leque aberto na posição em que
joga:

    python scripts/confere_enquadramento.py         # 12 amostras
    python scripts/confere_enquadramento.py 40      # mais amostras

Ele usa o `CameraStream` do app, com o mesmo foco, fps e resolução — o que se
mede aqui é o que o app vai ver, não uma aproximação.

## Como ler

A linha que decide é a ALTURA MEDIANA do índice na escala do modelo (1280).
O alvo é 100-130 px; abaixo de 100 a perda de detecção cresce nas três
gravações medidas. Os números e a ressalva estão em `app/enquadramento.py`.

As outras linhas são contexto, não veredito: a nitidez (se ela desabar com o
leque PARADO, o problema é FOCO — rode o `afina_foco.py`) e a margem até a
borda de baixo, que o `fan_borda` protege mas que o CLAUDE.md pede manter
folgada ("na BORDA do quadro não nasce carta").
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from afina_foco import nitidez_do_leque              # noqa: E402
from app.capture import CameraStream                 # noqa: E402
from app.config import config                        # noqa: E402
from app.detector import CardDetector, hand_instances  # noqa: E402
from app.enquadramento import alturas_no_modelo, avalia  # noqa: E402

AMOSTRAS = 12
ESPERA = 0.25      # entre amostras, para não medir o mesmo quadro
# Prazo para o PRIMEIRO quadro. Não é margem de sobra: o `CameraStream` tem 8 s
# de limite por backend e, se o pedido de 60 fps derrubar a câmera, ele desliga
# o pedido e REABRE — duas aberturas antes do primeiro quadro. Dormir um tempo
# fixo aqui fazia o script mentir "o app está aberto?" com a câmera livre.
PRAZO_PRIMEIRO = 25.0
ASSENTA = 1.0      # depois do primeiro quadro: foco/exposição ainda assentam


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else AMOSTRAS
    det = CardDetector(config.model_path, config.min_confidence,
                       imgsz=config.detect_imgsz,
                       agnostic_nms=config.agnostic_nms)
    cam = CameraStream(config.hand_cam_index,
                       config.frame_width, config.frame_height,
                       fps=config.cam_fps, foco=config.cam_foco,
                       exposicao=config.cam_exposicao)
    limite = time.time() + PRAZO_PRIMEIRO
    while cam.read() is None and time.time() < limite:
        time.sleep(0.2)
    if cam.read() is None:
        print(f"a câmera não entregou quadro em {PRAZO_PRIMEIRO:.0f}s — "
              f"o app está aberto?")
        cam.stop()
        return
    time.sleep(ASSENTA)
    print(f"câmera {config.hand_cam_index}: fps negociado "
          f"{cam.fps_negociado:.0f} | foco {cam.foco_negociado:.0f}")
    # O pedido de foco NÃO é garantido, e a falha é silenciosa: medido em
    # 24/09, a mesma câmera que aceitou `foco FIXO 95` numa abertura devolveu
    # -1 na seguinte. Foco no automático vale 15,18% de perda contra 3,75%
    # (18/09), então gravar sem conferir isto é jogar a sessão fora.
    if config.cam_foco and abs(cam.foco_negociado - config.cam_foco) > 1:
        print(f"!! o FOCO não pegou: pedimos {config.cam_foco}, a câmera diz "
              f"{cam.foco_negociado:.0f}. Feche tudo, reconecte a webcam e "
              f"rode de novo ANTES de gravar.")
    if (img := cam.read()) is not None and img.shape[1] != config.frame_width:
        print(f"!! a câmera abriu em {img.shape[1]}x{img.shape[0]}, não em "
              f"{config.frame_width}x{config.frame_height} — menos detalhe "
              f"chega ao modelo.")
    print("segure o leque na posição de JOGO\n")

    alturas: list[float] = []
    nitidezes: list[float] = []
    cartas: list[int] = []
    baixo: list[float] = []
    largura = float(config.frame_width)
    for _ in range(n):
        img = cam.read()
        if img is None:
            continue
        largura = float(img.shape[1])
        dets = det.detect(img)
        if not dets:
            cartas.append(0)
            time.sleep(ESPERA)
            continue
        # deduplica por POSIÇÃO antes de medir: as detecções cruas trazem dois
        # palpites do mesmo canto, e eles contariam como dois índices
        leque = hand_instances(dets)
        cartas.append(len(leque))
        alturas += alturas_no_modelo([d.box for d in leque], largura)
        nitidezes.append(nitidez_do_leque(img, leque))
        baixo.append(img.shape[0] - max(d.box[3] for d in leque))
        time.sleep(ESPERA)
    cam.stop()

    v = avalia(alturas)
    print(f"cartas lidas por quadro: {np.mean(cartas):.1f} "
          f"(mín {min(cartas, default=0)}, máx {max(cartas, default=0)})")
    if v.n:
        print(f"ALTURA do índice a 1280: p10 {v.p10:.0f}  "
              f"p50 {v.p50:.0f}  p90 {v.p90:.0f} px")
        print(f"  fração abaixo de 80 px: {100 * v.fracao_pequena:.0f}%   "
              f"(24/09 teve 23%, 18/09 teve 15% e 1%)")
        print(f"nitidez no leque: {np.median(nitidezes):.0f}   "
              f"(~4.000 é o bom; se desabar com o leque PARADO, é FOCO)")
        print(f"margem até a borda de baixo: {np.median(baixo):.0f} px")
    print(f"\n>>> {v.acao}")


if __name__ == "__main__":
    main()
