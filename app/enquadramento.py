"""Veredito sobre o ENQUADRAMENTO do leque, a partir da altura dos índices.

## Por que existe

Em 2026-09-24 gravei uma partida para confirmar o ganho da LUZ de 18/09 e a
medição não valeu — não por causa da luz, que estava ligada e medida (nitidez
no leque parado 3.990, a melhor do projeto), mas porque **o leque ficou mais
longe da câmera**. O índice chegou ao modelo com 97 px de altura contra 105 e
127 px das duas gravações de 18/09, e a perda de detecção saiu 5,53% contra
3,19% e 3,48%.

Antes daquela gravação eu conferi o foco (`afina_foco.py`) e a nitidez, e **não
conferi o tamanho do índice** — que é justamente o primeiro item que o
CLAUDE.md manda checar ("Enquadramento é metade do resultado", "antes de culpar
o modelo ou retreinar, confira o tamanho do índice no quadro"). Este módulo
existe para essa conferência custar 10 segundos em vez de uma gravação.

## O que a medição sustenta

Perda de detecção repartida pela altura do índice, medida DENTRO de cada
gravação (que é o controle que separa "o leque estava longe" de "a imagem
estava pior"):

| altura a 1280 | 24/09 | 18/09 mais luz | 18/09 luz antes |
|---|---|---|---|
| < 80 px  | 11,60% | 7,35% | 19,43% |
| 80-100   |  5,38% | 1,52% |  8,73% |
| 100-120  |  1,90% | 1,04% |  3,18% |
| >= 120   |   —    | 8,78% |  2,42% |

**Abaixo de 100 px a perda cresce nas TRÊS gravações**, e é a parte firme. Acima
de 120 o dado é ambíguo (8,78% numa, 2,42% na outra) e o modelo é preso à
escala, então "quanto maior, melhor" NÃO está medido — por isso o alvo é uma
FAIXA, não um piso.

A fração do leque na pior faixa é reportada como contexto e **não** decide o
veredito: são três gravações (22,8% · 14,7% · 1,4%), amostra fina demais para
virar limiar. Quem decide é a mediana.
"""
from dataclasses import dataclass

# A faixa em que a perda foi mais baixa nas três gravações medidas. O teto não
# é um limite de qualidade medido: é o ponto em que o dado deixa de sustentar
# "maior é melhor".
ALVO_MIN = 100.0
ALVO_MAX = 130.0
# Abaixo disto a perda dobra ou triplica em todas as gravações medidas.
PEQUENO = 80.0
# O modelo vê o lado maior reduzido a isto; a altura em px do quadro cru é
# outra grandeza. Comparar as duas direto é a armadilha de unidade que o
# CLAUDE.md já registra na razão largura/altura do rótulo YOLO.
LADO_MODELO = 1280.0


@dataclass
class Veredito:
    """Resultado da conferência. `ok` é o que decide gravar ou reposicionar."""
    n: int
    p10: float
    p50: float
    p90: float
    fracao_pequena: float   # parte dos índices abaixo de PEQUENO
    ok: bool
    acao: str


def alturas_no_modelo(caixas, largura_quadro: float) -> list[float]:
    """Altura de cada caixa na escala em que o MODELO a vê.

    O detector devolve px do quadro cru (1920 de largura) e o Ultralytics
    reduz o lado maior a `imgsz`. Medir no quadro cru superestima o índice em
    50% e faria qualquer enquadramento parecer bom.
    """
    if largura_quadro <= 0:
        return []
    k = LADO_MODELO / largura_quadro
    return [(c[3] - c[1]) * k for c in caixas]


def _percentil(vals: list[float], p: float) -> float:
    """Percentil por interpolação linear, sem depender do numpy."""
    if not vals:
        return 0.0
    ordenado = sorted(vals)
    if len(ordenado) == 1:
        return ordenado[0]
    pos = (len(ordenado) - 1) * p
    baixo = int(pos)
    alto = min(baixo + 1, len(ordenado) - 1)
    return ordenado[baixo] + (ordenado[alto] - ordenado[baixo]) * (pos - baixo)


def avalia(alturas: list[float]) -> Veredito:
    """Veredito a partir das alturas já na escala do modelo.

    Quadro sem carta NÃO é enquadramento ruim, é ausência de medida — e dizer
    "está bom" ali seria pior que calar, porque é o caso em que o operador
    acha que conferiu.
    """
    if not alturas:
        return Veredito(0, 0.0, 0.0, 0.0, 0.0, False,
                        "nenhuma carta no quadro — segure o leque na posição "
                        "de jogo e rode de novo")
    p50 = _percentil(alturas, 0.50)
    pequenos = sum(1 for h in alturas if h < PEQUENO) / len(alturas)
    v = Veredito(len(alturas), _percentil(alturas, 0.10), p50,
                 _percentil(alturas, 0.90), pequenos, False, "")
    if p50 < PEQUENO:
        v.acao = (f"APROXIME o leque da câmera: índice a {p50:.0f} px, muito "
                  f"menor que os {ALVO_MIN:.0f}-{ALVO_MAX:.0f} px em que a "
                  f"perda é mais baixa")
    elif p50 < ALVO_MIN:
        v.acao = (f"aproxime um pouco: índice a {p50:.0f} px, abaixo dos "
                  f"{ALVO_MIN:.0f} px do alvo (foi o defeito de 24/09)")
    elif p50 > ALVO_MAX:
        v.acao = (f"afaste um pouco: índice a {p50:.0f} px, acima dos "
                  f"{ALVO_MAX:.0f} px — acima de 120 o dado é ambíguo e o "
                  f"modelo é preso à escala")
    else:
        v.ok = True
        v.acao = f"enquadramento OK: índice a {p50:.0f} px, dentro do alvo"
    return v
