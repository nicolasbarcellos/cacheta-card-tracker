"""Quantas cartas o modelo INVENTA onde não existe carta nenhuma.

O `eval_classes.py` mede o outro lado — se a carta que está lá é lida certo. Ele
é cego para este defeito, porque só olha imagens QUE TÊM carta: um modelo que
enxerga cartas na parede tira 100% nele. Foi assim que o problema chegou até
2026-08-20 sem aparecer em número nenhum, enquanto ao vivo o leitor mostrava
uma "mão" de duas cartas lidas do logo *"10COC LEAGUE"* pintado na sala.

A conta é direta, porque a verdade é conhecida por construção: **nestas imagens
o número certo de detecções é ZERO**.

    python training/eval_negativos.py models/cards.pt
    python training/eval_negativos.py models/cards.pt training/datasets/negativos-holdout
    python training/eval_negativos.py models/cards_backup_8.pt   # o anterior

Compare sempre os dois modelos no MESMO conjunto, e prefira um conjunto que
NÃO entrou no treino — negativo visto no treino diz o que o modelo decorou, não
o que ele aprendeu. É para isso que `datasets/negativos-holdout/` existe.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config                     # noqa: E402
from app.detector import hand_instances           # noqa: E402

RAIZ = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modelo", nargs="?", default="models/cards.pt")
    ap.add_argument("conjunto", nargs="?", type=Path,
                    default=RAIZ / "datasets" / "negativos")
    ap.add_argument("--conf", type=float, default=config.min_confidence,
                    help="limiar da detecção (padrão: o do app)")
    args = ap.parse_args()

    import cv2
    from app.detector import CardDetector

    imagens = sorted(args.conjunto.glob("*/images/*.jpg"))
    if not imagens:
        imagens = sorted(args.conjunto.glob("images/*.jpg"))
    if not imagens:
        raise SystemExit(f"nenhuma imagem em {args.conjunto}")

    det = CardDetector(args.modelo, args.conf, imgsz=config.detect_imgsz,
                       agnostic_nms=config.agnostic_nms)
    print(f"modelo: {args.modelo}")
    print(f"conjunto: {len(imagens)} imagens SEM carta ({args.conjunto})\n")

    sujas = 0
    total = 0
    rotulos: Counter = Counter()
    confs: list[float] = []
    piores: list[tuple] = []
    for n, img in enumerate(imagens, 1):
        frame = cv2.imread(str(img))
        if frame is None:
            continue
        # deduplicado por posição, como no app: duas leituras do mesmo ponto
        # são um erro só, e é assim que o pipeline as conta
        dets = hand_instances(det.detect(frame))
        if dets:
            sujas += 1
            total += len(dets)
            for d in dets:
                rotulos[d.card.code] += 1
                confs.append(d.confidence)
            piores.append((max(d.confidence for d in dets), len(dets),
                           img.name))
        if n % 25 == 0:
            print(f"  {n}/{len(imagens)}...")

    print(f"\n=== {len(imagens)} imagens sem carta ===")
    print(f"  imagens com ALGUMA carta inventada: {sujas} "
          f"({100 * sujas / len(imagens):.1f}%)")
    print(f"  cartas inventadas no total:         {total} "
          f"({total / len(imagens):.2f} por imagem)")
    if confs:
        confs.sort()
        print(f"  confianca das inventadas: p50={confs[len(confs) // 2]:.2f} "
              f"max={confs[-1]:.2f}")
        print("\n  rotulos mais inventados:")
        for code, k in rotulos.most_common(8):
            print(f"    {code:4s} {k:4d}")
        print("\n  piores imagens:")
        for conf, k, nome in sorted(piores, reverse=True)[:8]:
            print(f"    {nome}  {k} cartas, pico {conf:.2f}")


if __name__ == "__main__":
    main()
