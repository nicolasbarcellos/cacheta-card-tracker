"""Perda de detecção repartida por ROTAÇÃO do índice — o alvo aberto do projeto.

A média global esconde o defeito. Medido em 2026-09-03 nas duas gravações com
vídeo recente e com três modelos diferentes: o índice **muito deitado** perde
11-14% das detecções contra 1,4-4,4% do índice em pé — um gradiente de 3x a 8x
que se manteve em TODAS as combinações. E ele pesa: 8-19% do leque.

## Por que precisou de instrumento novo (os três antigos são cegos a isto)

- **`eval_classes.py` num `datasets/real/<partida>` dá 100,0% de detecção POR
  CONSTRUÇÃO.** O `extrai_gravacao.py` só guarda frame em que `alinhado()`
  passa, isto é, em que TODAS as cartas foram detectadas — o conjunto é purgado
  exatamente da falha que se quer medir. O CLAUDE.md publicava "índices
  detectados: 100,0%" desde 20/08 sem que isso levantasse suspeita.
- **`holdout-ranks` tem 0,7% de índice deitado** (contra 30,2% dos rótulos das
  partidas reais): ele não consegue enxergar a condição.
- **A taxa global do `extrai_dificeis --so-analise` mistura as faixas.** Foi com
  ela que a abertura do gerador (`cards_backup_12`) foi julgada em 25/08 — e a
  repartição mostra que o ganho global dele NÃO veio da rotação: ele melhora "em
  pé" e "inclinado" e PIORA as duas faixas deitadas.

É a terceira vez que um instrumento de aceite deste projeto aprova um erro que
aparece ao vivo. As outras duas: o K♠→A♠ medido em sintético (12/08) e a carta
inventada, que só o `eval_negativos.py` vê (20/08).

## De onde vem a verdade

Da VAGA do `FanReader`, como no `extrai_dificeis.py`: ela tem rótulo estabelecido
pela votação ponderada dos frames em que a carta FOI vista, e a rotação sai da
última caixa em que aquela vaga apareceu. Não é ground truth rotulado à mão — é
o mesmo padrão que o repositório já aceita para medir perda.

**Compare só arquivos de detecção do MESMO vídeo.** O `--redetectar` do MJPG não
é comparável com o número ao vivo; isso é regra do repositório.

    python scripts/replay.py gravacoes/<data> --redetectar models/cards_novo.pt
    python training/eval_rotacao.py gravacoes/<data> \\
        sessao-cards.jsonl sessao-cards_novo.jsonl

ATENÇÃO ao ler a diferença entre dois modelos: medido em 2026-09-03, duas
rodadas de treino com a MESMA receita diferiram em **1,06 ponto** de perda
global numa gravação e 0,15 na outra, em direções opostas. O piso de ruído é
maior do que os 0,3 ponto que o CLAUDE.md estimava — exija ganho nas DUAS
gravações antes de concluir qualquer coisa.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config                            # noqa: E402
from app.main import build_pipeline, process_frame       # noqa: E402
from app.replay import carrega, detections_do_registro   # noqa: E402
from app.tracker import GameTracker                      # noqa: E402

# Proporção largura/altura da caixa, em PIXELS — o proxy de rotação que o
# projeto já usa (índice em pé ~0,6; deitado >=1,0). CUIDADO ao comparar com
# rótulo YOLO: lá a largura e a altura vêm NORMALIZADAS pelo quadro, então a
# razão do rótulo já vem multiplicada por (H/W) = 9/16 e precisa ser convertida.
FAIXAS = [(0.0, 0.7, "em pe"), (0.7, 0.9, "inclinado"),
          (0.9, 1.0, "quase deit"), (1.0, 1.2, "deitado"),
          (1.2, 99.0, "muito deit")]


def mede(arquivo: Path):
    """(vistas, perdas, perdidas, total) por faixa de rotação."""
    registros = carrega(arquivo)
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()
    vistas = {f[2]: 0 for f in FAIXAS}
    perdas = {f[2]: 0 for f in FAIXAS}
    ultima: dict = {}
    total = perdidas = 0
    for rec in registros:
        if rec.get("t") != "frame":
            continue
        process_frame(detections_do_registro(rec, config.min_confidence),
                      tracker, leitor, trava, verbose=False)
        # leitor congelado é oclusão declarada por ele mesmo: não é perda
        if leitor.congelado:
            continue
        vagas = [v for v in leitor.slots_debug()
                 if v["n"] >= config.fan_min_appear and v["label"]]
        if len(vagas) < 4:
            continue
        leque = leitor.ultimo_leque
        for v in vagas:
            total += 1
            if v["misses"] == 0:
                melhor, dist_min = None, config.fan_match_dist
                for d in leque:
                    dist = (((d.box[0] + d.box[2]) / 2 - v["x"]) ** 2
                            + ((d.box[1] + d.box[3]) / 2 - v["y"]) ** 2) ** 0.5
                    if dist < dist_min:
                        melhor, dist_min = d, dist
                if melhor is not None:
                    ultima[v["label"]] = (
                        (melhor.box[2] - melhor.box[0])
                        / max(melhor.box[3] - melhor.box[1], 1))
            razao = ultima.get(v["label"])
            if razao is None:
                continue          # ainda não se viu a caixa desta vaga
            faixa = next(n for lo, hi, n in FAIXAS if lo <= razao < hi)
            vistas[faixa] += 1
            if v["misses"] >= 1:
                perdas[faixa] += 1
                perdidas += 1
    return vistas, perdas, perdidas, total


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("dets", nargs="+",
                    help="arquivos de detecção do MESMO vídeo (padrão: "
                         "sessao.jsonl)")
    args = ap.parse_args()

    resultados = {}
    for nome in args.dets:
        caminho = Path(nome) if Path(nome).exists() else args.gravacao / nome
        if not caminho.exists():
            raise SystemExit(f"nao achei {caminho}")
        rotulo = caminho.stem.replace("sessao-", "").replace("sessao", "ao vivo")
        resultados[rotulo] = mede(caminho)
        print(f"  medido {caminho.name}", flush=True)

    base = list(resultados.values())[0][0]
    total_vistas = max(sum(base.values()), 1)
    larg = max(max(len(k) for k in resultados), 10) + 2
    print("")
    print(f"=== {args.gravacao.name}: PERDA DE DETECCAO por rotacao ===")
    cabecalho = (f"{'faixa':<12}"
                 + "".join(f"{k:>{larg}}" for k in resultados)
                 + f"{'fatia':>9}")
    print(cabecalho)
    print("-" * len(cabecalho))
    for _lo, _hi, nome in FAIXAS:
        linha = f"{nome:<12}"
        for _k, (vistas, perdas, _p, _t) in resultados.items():
            n = vistas[nome]
            linha += f"{(100 * perdas[nome] / n if n else 0.0):>{larg - 1}.2f}%"
        linha += f"{100 * base[nome] / total_vistas:>8.1f}%"
        print(linha)
    print("-" * len(cabecalho))
    linha = f"{'GLOBAL':<12}"
    for _k, (_v, _p, perdidas, total) in resultados.items():
        linha += f"{100 * perdidas / max(total, 1):>{larg - 1}.2f}%"
    print(linha)
    print("\n  a coluna 'fatia' e do PRIMEIRO arquivo: quanto do leque cai em "
          "cada faixa.\n  diferenca menor que ~1 ponto entre modelos e ruido de "
          "rodada -- ver o docstring.")


if __name__ == "__main__":
    main()
