"""A nota da TELA contra a mão VERDADEIRA — só nas gravações com `verdade.json`.

    python scripts/mede_verdade.py                       # todas que têm verdade
    python scripts/mede_verdade.py gravacoes/20260917-174349
    python scripts/mede_verdade.py gravacoes/... --dets sessao-cards_novo.jsonl

O irmão do `mede_leitura.py`, e o complemento dele: aquele roda em qualquer
gravação mas cobra da tela o erro do modelo; este só roda onde a mão é
conhecida, e aí não se engana. O porquê está em `app/verdade.py`.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.replay import aplica_overrides, carrega  # noqa: E402
from app.verdade import carrega_verdade, imprime_verdade, mede_verdade  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent / "gravacoes"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacoes", type=Path, nargs="*")
    ap.add_argument("--dets", type=Path,
                    help="usa outro arquivo de detecções (ex.: de --redetectar)")
    ap.add_argument("--set", action="append", default=[], metavar="NOME=VALOR")
    args = ap.parse_args()

    alvos = args.gravacoes or sorted(p.parent for p in RAIZ.glob("*/verdade.json"))
    aplicados = aplica_overrides(args.set)
    if aplicados:
        print(f"config: {aplicados}")
    for g in alvos:
        verdade = carrega_verdade(g)
        if verdade is None:
            print(f"--- {g.name}: sem verdade.json, pulando")
            continue
        origem = g / "sessao.jsonl"
        if args.dets:
            origem = args.dets if args.dets.exists() else g / args.dets
        imprime_verdade(mede_verdade(carrega(origem), verdade), g.name)


if __name__ == "__main__":
    main()
