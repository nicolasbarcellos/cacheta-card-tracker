"""A nota do projeto desde 2026-08-19: a mão na TELA é a mão real, agora?

Três números, todos medidos por replay contra uma partida gravada — atraso,
contradição e trocas. O que cada um significa, e as decisões de medição que
mudam o resultado, estão em `app/leitura.py`.

    python scripts/mede_leitura.py gravacoes/20260819-162252
    python scripts/mede_leitura.py gravacoes/... --set lock_frames=30
    python scripts/mede_leitura.py gravacoes/... --varre lock_frames=10,20,30,45,60
    python scripts/mede_leitura.py gravacoes/... --varre fan_vao_grupo=0,2.5 --resumo
    python scripts/mede_leitura.py gravacoes/... --dets sessao-cards_novo.jsonl

Este é o irmão do `scripts/replay.py`, que dá a outra nota — a de compra e
descarte. Aquela mede EVENTO e precisa de gabarito revisado à mão; esta mede a
TELA e não precisa de gabarito nenhum, porque a verdade de referência é o que o
próprio quadro mostra. É por isso que ela roda em qualquer gravação, inclusive
nas que ninguém revisou.

MESMO LIMITE do replay: as detecções gravadas já passaram pelo `min_confidence`
da partida (0,30). Dá para SUBIR o limiar, nunca baixá-lo — para isso é preciso
re-detectar do vídeo (`scripts/replay.py --redetectar`), e aí este script lê o
`sessao-<modelo>.jsonl` resultante com `--dets`.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.leitura import imprime, mede           # noqa: E402
from app.replay import aplica_overrides, carrega  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--dets", type=Path,
                    help="usa outro arquivo de detecções (ex.: de --redetectar)")
    ap.add_argument("--set", action="append", default=[], metavar="NOME=VALOR",
                    help="sobrescreve um parâmetro da config (ou merge_factor)")
    ap.add_argument("--varre", metavar="NOME=v1,v2,v3",
                    help="mede uma vez por valor e compara")
    ap.add_argument("--conf", type=float, default=0.80,
                    help="confiança a partir da qual uma carta vista e ausente "
                         "da tela conta como contradição (padrão: 0.80)")
    ap.add_argument("--resumo", action="store_true",
                    help="só os números, sem as cartas e os exemplos")
    args = ap.parse_args()

    origem = args.gravacao / "sessao.jsonl"
    if args.dets:
        origem = args.dets if args.dets.exists() else args.gravacao / args.dets
    if not origem.exists():
        raise SystemExit(f"sem detecções em {origem}")
    registros = carrega(origem)

    if args.varre:
        nome, _, valores = args.varre.partition("=")
        for valor in valores.split(","):
            aplica_overrides(args.set + [f"{nome}={valor}"])
            # numa varredura o que interessa é a CURVA dos três números, não a
            # lista de cartas de cada configuração
            imprime(mede(registros, conf_alta=args.conf), f"{nome}={valor}",
                    detalhar=False)
        return

    aplicados = aplica_overrides(args.set)
    if aplicados:
        print(f"config: {aplicados}")
    imprime(mede(registros, conf_alta=args.conf), args.gravacao.name,
            detalhar=not args.resumo)


if __name__ == "__main__":
    main()
