"""A TELA contra a mão VERDADEIRA, nas gravações em que ela é conhecida.

O `app/leitura.py` não tem gabarito: a referência dele é o próprio quadro, ou
seja, a leitura do MODELO. Isso o deixa rodar em qualquer gravação, e é também o
defeito dele — quando o modelo erra, a métrica cobra o erro da tela. Aconteceu
quatro vezes no projeto (a carta à parte, o leitor congelado, o empate de x, e
em 2026-09-28 a ordem de 17/09 17:43, onde a tela mostrava a mão certa e a
métrica marcava 4,4% de ordem errada porque o modelo trocava o 5♦ com um 3♦).

Aqui a referência é a mão que o operador DISSE, gravada em
`gravacoes/<data>/verdade.json`:

    {"mao_inicial": "7C 3D JS ...",   # da esquerda para a direita
     "ordem_fixa": true}              # a ordem não mudou na gravação

mais as jogadas do `gabarito_corrigido.json`, quando houver. Com jogadas, a
ORDEM não é conhecida (o jogador encaixa a carta onde quer) e só o conjunto é
cobrado.

Três decisões de medição:

1. **Só conta frame com o leque no quadro** — ao menos metade da mão verdadeira
   detectada. Sem isso o denominador vira "tempo de gravação", o erro da
   cobertura de 20/08.
2. **A transição não conta.** Depois de cada jogada a tela tem de esperar a
   leitura nova ficar estável (`lock_frames`, ~0,7 s); cobrar isso é medir o
   atraso, que já tem número próprio. `MARGEM_JOGADA` segundos depois de cada
   jogada ficam fora.
3. **Depois da última jogada não há verdade** — o gabarito acaba ali. Com zero
   jogadas (mão fixa) a gravação inteira vale.
"""

import json
from collections import Counter
from pathlib import Path

from app.config import config
from app.main import build_pipeline, process_frame
from app.replay import detections_do_registro
from app.tracker import GameTracker

MARGEM_JOGADA = 1.5


def carrega_verdade(gravacao: Path) -> dict | None:
    """{mao_inicial: [...], ordem_fixa: bool, jogadas: [...]}, ou None."""
    arq = gravacao / "verdade.json"
    if not arq.exists():
        return None
    v = json.loads(arq.read_text(encoding="utf-8"))
    jogadas = []
    gab = gravacao / "gabarito_corrigido.json"
    if gab.exists():
        jogadas = json.loads(gab.read_text(encoding="utf-8"))["jogadas"]
    return {"mao_inicial": v["mao_inicial"].split(),
            "ordem_fixa": bool(v.get("ordem_fixa", False)),
            "margem_antes": float(v.get("margem_antes", 0.0)),
            "jogadas": sorted(jogadas, key=lambda j: j["ts"])}


def mao_em(ts: float, mao0: list[str], jogadas: list[dict],
           margem_antes: float = 0.0):
    """(mão verdadeira no instante `ts`, está em transição?) — ou None.

    None quando `ts` passa da última jogada: dali em diante não há verdade.

    `margem_antes` existe porque nem todo gabarito tem o instante FÍSICO da
    jogada. Os de 17/09 e 25/09 foram cravados olhando o vídeo; os de 11/08 e
    12/08 guardam o instante em que o sistema EMITIU o evento — que, com o
    `lock_frames = 60` daquela época, vinha segundos DEPOIS de a carta mudar.
    Sem a margem, esse trecho seria cobrado da tela como mão errada.
    """
    if jogadas and ts > jogadas[-1]["ts"]:
        return None
    mao = Counter(mao0)
    transicao = any(0 <= j["ts"] - ts < margem_antes for j in jogadas)
    for j in jogadas:
        if j["ts"] > ts:
            break
        if ts - j["ts"] < MARGEM_JOGADA:
            transicao = True
        if j["tipo"] == "draw":
            mao[j["carta"]] += 1
        else:
            mao[j["carta"]] -= 1
            if mao[j["carta"]] <= 0:
                del mao[j["carta"]]
    return mao, transicao


def mede_verdade(registros: list[dict], verdade: dict) -> dict:
    """Passa a gravação pelo pipeline de verdade e compara a tela com a mão."""
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()
    mao0 = verdade["mao_inicial"]
    jogadas = verdade["jogadas"]
    fixa = verdade["ordem_fixa"] and not jogadas

    n = transicao = conjunto_ok = faltando = sobrando = 0
    ordem_ok = ordem_n = 0
    por_carta_falta: Counter = Counter()
    por_carta_sobra: Counter = Counter()
    for rec in registros:
        if rec["t"] != "frame":
            continue
        dets = detections_do_registro(rec, config.min_confidence)
        process_frame(dets, tracker, leitor, trava, verbose=False)
        estado = mao_em(rec.get("ts", 0.0), mao0, jogadas,
                        verdade.get("margem_antes", 0.0))
        if estado is None:
            continue
        real, em_transicao = estado
        if 2 * len(dets) < sum(real.values()):
            continue                      # o leque não está no quadro
        if em_transicao:
            transicao += 1
            continue
        n += 1
        tela = [c.code for c in tracker.hand_view]
        falta = real - Counter(tela)
        sobra = Counter(tela) - real
        if not falta and not sobra:
            conjunto_ok += 1
            if fixa:
                ordem_n += 1
                ordem_ok += tela == mao0
        if falta:
            faltando += 1
            por_carta_falta.update(falta.elements())
        if sobra:
            sobrando += 1
            por_carta_sobra.update(sobra.elements())
    return {"frames": n, "transicao": transicao, "conjunto_ok": conjunto_ok,
            "faltando": faltando, "sobrando": sobrando,
            "ordem_ok": ordem_ok, "ordem_n": ordem_n, "ordem_cobrada": fixa,
            "por_carta_falta": por_carta_falta,
            "por_carta_sobra": por_carta_sobra}


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def imprime_verdade(r: dict, nome: str):
    n = r["frames"]
    print(f"--- {nome}  (contra a mão VERDADEIRA)")
    print(f"  {n} frames com o leque no quadro "
          f"({r['transicao']} de transição fora da conta)")
    print(f"  MÃO CERTA na tela: {r['conjunto_ok']}/{n} ({pct(r['conjunto_ok'], n)})")
    print(f"  faltando carta: {pct(r['faltando'], n)}   "
          f"sobrando carta: {pct(r['sobrando'], n)}")
    if r["ordem_cobrada"]:
        print(f"  ORDEM certa, com a mão certa: {r['ordem_ok']}/{r['ordem_n']} "
              f"({pct(r['ordem_ok'], r['ordem_n'])})")
    else:
        print("  ordem: não cobrada (a mão mudou; o gabarito não diz a ordem)")
    if r["por_carta_falta"]:
        print("  faltou na tela: " + "  ".join(
            f"{c} {k}" for c, k in r["por_carta_falta"].most_common(5)))
    if r["por_carta_sobra"]:
        print("  sobrou na tela: " + "  ".join(
            f"{c} {k}" for c, k in r["por_carta_sobra"].most_common(5)))
