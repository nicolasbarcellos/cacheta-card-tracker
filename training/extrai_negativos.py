"""Frames SEM carta nenhuma viram dado de treino — o que ensina a NÃO detectar.

Medido em 2026-08-20: o modelo lê o logo *"10COC ... LEAGUE"* pintado na parede
da sala como `10C` e `QC`, e textura de reboco como `5S 4D KS`. Desde a virada
de escopo de 19/08 essas cartas inventadas chegam à TELA — o `StableHand`
aceita qualquer tamanho estável, e uma parede é o objeto mais estável que
existe, mais estável que uma mão de verdade. Na partida de 15:50 são ~30 s de
tela mostrando uma "mão" de duas cartas que não existem.

Nenhum parâmetro do pipeline separa isso (medido: a parede anda 1,2 px por
frame contra 1,8 px do leque segurado firme, e o pico de confiança do fantasma
é 0,94 — a mesma de uma carta boa). É defeito de MODELO, e o conserto é o mesmo
método que matou o A♠ em 18/08: dado REAL, tirado do que já está em disco.

Aqui a matéria-prima é ainda mais barata que a do `extrai_gravacao.py`, porque
não precisa nem de gabarito: **o rótulo de um frame sem carta é o arquivo
vazio**. Toda gravação tem minutos de sala vazia, e nenhum deles esteve num
treino até hoje.

O RISCO é um só, e é o inverso do risco do `extrai_gravacao.py`: incluir um
frame que TEM carta. Um índice visível na imagem e sem rótulo ensina o modelo
que aquele padrão é fundo — o CLAUDE.md já registra esse tiro no pé em outro
contexto. Três guardas, nesta ordem:

1. **Bloco de jogo com margem.** Frame em que o modelo vê `JOGO_MIN`+ cartas é
   jogo; a margem de segurança (`--margem`, 20 s por padrão) se estende para os
   dois lados. Nada dentro disso vira negativo, mesmo que o modelo não esteja
   detectando nada naquele instante exato — é justamente aí que a mão está indo
   e voltando do quadro.
2. **Espaçamento.** Frames vizinhos a 30 fps são quase idênticos e inflariam o
   conjunto com a mesma imagem; `--passo` separa as amostras.
3. **Auditoria por folha de contato.** As três guardas do `extrai_gravacao.py`
   vieram de OLHAR as imagens, não de raciocinar sobre o código. Aqui vale o
   mesmo: `review/` traz o frame com as detecções falsas marcadas em vermelho,
   e apagar a imagem rejeita o frame (é o mecanismo que o `finetune_local.py`
   já respeita).

Os frames em que o modelo DISPAROU (os "duros") são os que valem; os frames
limpos entram em menor número, para dar fundo variado sem afogar o conjunto.

    python training/extrai_negativos.py gravacoes/20260812-154737
    python training/extrai_negativos.py gravacoes/... --max-duros 120 --max-faceis 100

ATENÇÃO ao escolher a gravação: negativo tirado da mesma partida em que se vai
MEDIR o fantasma não prova nada. Em 2026-08-20 os negativos saíram de 12/08 e a
medição foi feita em 19/08 15:50, que tem o mesmo logo em outro ângulo.
"""

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config                      # noqa: E402
from app.detector import hand_instances            # noqa: E402
from app.replay import carrega, detections_do_registro   # noqa: E402

RAIZ = Path(__file__).resolve().parent
JOGO_MIN = 6          # a partir de N cartas no frame, é jogo (não é fantasma)
CONTATO = 24          # miniaturas por folha de contato


def blocos_de_jogo(frames, fps, margem_s):
    """Máscara de "aqui tem jogo", já dilatada pela margem de segurança."""
    margem = int(margem_s * fps)
    perto = [False] * len(frames)
    for k, (_i, _v, _ts, n, _c) in enumerate(frames):
        if n >= JOGO_MIN:
            for j in range(max(0, k - margem), min(len(frames), k + margem + 1)):
                perto[j] = True
    return perto


def amostra(candidatos, quantos, passo):
    """Escolhe `quantos` frames espaçados de pelo menos `passo` índices."""
    if not candidatos or quantos <= 0:
        return []
    escolhidos = []
    ultimo = None
    # varre em ordem de tempo, mas com passo adaptado para cobrir a gravação
    largura = max(passo, len(candidatos) // max(quantos, 1))
    for c in candidatos:
        if ultimo is None or c["i"] - ultimo >= largura:
            escolhidos.append(c)
            ultimo = c["i"]
        if len(escolhidos) >= quantos:
            break
    return escolhidos


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--saida", type=Path,
                    default=RAIZ / "datasets" / "negativos")
    ap.add_argument("--margem", type=float, default=20.0,
                    help="segundos de margem em volta de cada trecho de jogo")
    ap.add_argument("--passo", type=int, default=8,
                    help="frames mínimos entre duas amostras vizinhas")
    ap.add_argument("--max-duros", type=int, default=120,
                    help="teto de frames em que o modelo DETECTOU algo (os que "
                         "valem: é o erro que se quer desensinar)")
    ap.add_argument("--max-faceis", type=int, default=80,
                    help="teto de frames limpos (fundo variado)")
    args = ap.parse_args()

    registros = carrega(args.gravacao / "sessao.jsonl")
    frames, brutos = [], {}
    for r in registros:
        if r["t"] != "frame":
            continue
        dets = hand_instances(detections_do_registro(r, config.min_confidence))
        frames.append((r["i"], r.get("v", -1), r.get("ts", 0.0), len(dets),
                       max((d.confidence for d in dets), default=0.0)))
        if dets:
            brutos[r["i"]] = dets
    if not frames:
        raise SystemExit("gravação sem frames")

    fps = len(frames) / max(frames[-1][2], 1.0)
    perto = blocos_de_jogo(frames, fps, args.margem)
    fora = [{"i": i, "v": v, "ts": ts, "n": n}
            for (i, v, ts, n, _c), p in zip(frames, perto) if not p and v >= 0]
    duros = [c for c in fora if c["n"] > 0]
    faceis = [c for c in fora if c["n"] == 0]
    print(f"{len(frames)} frames a {fps:.1f} fps | fora do jogo (margem "
          f"{args.margem:.0f}s): {len(fora)} com vídeo")
    print(f"  {len(duros)} com detecção FALSA (os que valem) · "
          f"{len(faceis)} limpos")

    escolhidos = (amostra(duros, args.max_duros, args.passo)
                  + amostra(faceis, args.max_faceis, args.passo))
    escolhidos.sort(key=lambda c: c["i"])
    if not escolhidos:
        raise SystemExit("nenhum frame fora do jogo — gravação só de partida?")

    destino = args.saida / args.gravacao.name
    for sub in ("images", "labels", "review"):
        (destino / sub).mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.gravacao / "mao.avi"))
    if not cap.isOpened():
        raise SystemExit(f"não abriu o vídeo em {args.gravacao}")

    miniaturas, salvos = [], 0
    for c in escolhidos:
        cap.set(cv2.CAP_PROP_POS_FRAMES, c["v"])
        ok, frame = cap.read()
        if not ok:
            continue
        nome = f"{args.gravacao.name}-{c['i']:06d}"
        cv2.imwrite(str(destino / "images" / f"{nome}.jpg"), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        # O RÓTULO É O ARQUIVO VAZIO: em YOLO, imagem sem caixa nenhuma é uma
        # "background image" e ensina o modelo a não disparar ali. Precisa
        # EXISTIR — o `collect` do finetune_local.py pula imagem sem label.
        (destino / "labels" / f"{nome}.txt").write_text("")
        # revisão: o que o modelo VIU de errado, em vermelho, para a auditoria
        rev = frame.copy()
        for d in brutos.get(c["i"], []):
            x1, y1, x2, y2 = (int(v) for v in d.box)
            cv2.rectangle(rev, (x1, y1), (x2, y2), (0, 0, 255), 3)
            cv2.putText(rev, f"{d.card.code} {d.confidence:.2f}", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        cv2.imwrite(str(destino / "review" / f"{nome}.jpg"), rev,
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
        miniaturas.append(cv2.resize(rev, (480, 270)))
        salvos += 1
    cap.release()

    # folhas de contato: a auditoria é olhar TUDO de uma vez, não abrir 200
    # arquivos. Foi assim que as guardas do extrai_gravacao.py apareceram.
    for n0 in range(0, len(miniaturas), CONTATO):
        lote = miniaturas[n0:n0 + CONTATO]
        linhas = []
        for k in range(0, len(lote), 4):
            fila = lote[k:k + 4]
            while len(fila) < 4:
                fila.append(fila[0] * 0)
            linhas.append(cv2.hconcat(fila))
        folha = cv2.vconcat(linhas)
        cv2.imwrite(str(destino / f"contato-{n0 // CONTATO:02d}.jpg"), folha,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])

    print(f"\n{salvos} negativos em {destino}")
    print(f"AUDITE as folhas de contato {destino}/contato-*.jpg ANTES de "
          f"treinar: nenhuma pode ter carta de verdade no quadro.")
    print("Rejeitar um frame = apagar a imagem dele em review/.")


if __name__ == "__main__":
    main()
