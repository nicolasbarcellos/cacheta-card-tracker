"""Nota de uma partida contra o gabarito revisado à mão.

Código puro (sem OpenCV, sem YOLO), como o `tracker` — é o que permite testar.

A meta de aceite do projeto (≥95% dos descartes e ≥90% das compras corretos) é
sobre as jogadas que ACONTECERAM, não sobre os eventos que o sistema resolveu
emitir. A diferença não é detalhe: um sistema que emitisse um único descarte na
partida inteira e acertasse aquele teria 100% de "eventos corretos" e seria
inútil. Por isso a conta é

    acerto = acertos / (acertos + carta_errada + perdidos)

e os fantasmas (evento sem jogada real) são reportados à parte — eles não
diminuem o acerto, mas sujam o overlay e têm de ser vistos.

O casamento entre a lista emitida e o gabarito é feito por SUBSEQUÊNCIA COMUM
MÁXIMA, não posição a posição. Se o sistema perde a terceira jogada, tudo
depois dela sai deslocado de uma posição, e uma comparação posicional marcaria
a partida inteira como errada a partir dali — mediria o deslocamento, não o
acerto.

Nos buracos que sobram do casamento, uma jogada real e um evento do MESMO tipo
que ficaram lado a lado são o mesmo acontecimento lido com a carta errada; só
o que sobra depois disso é perda (jogada sem evento) ou fantasma (evento sem
jogada).
"""


def _chave(e) -> tuple:
    return (e["tipo"], e["carta"])


def _subsequencia_comum(g: list, e: list) -> list[tuple[int, int]]:
    """Índices casados (i_gabarito, i_emitido) da maior subsequência comum."""
    n, m = len(g), len(e)
    tab = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if _chave(g[i]) == _chave(e[j]):
                tab[i][j] = tab[i + 1][j + 1] + 1
            else:
                tab[i][j] = max(tab[i + 1][j], tab[i][j + 1])
    pares, i, j = [], 0, 0
    while i < n and j < m:
        if _chave(g[i]) == _chave(e[j]):
            pares.append((i, j))
            i, j = i + 1, j + 1
        elif tab[i + 1][j] >= tab[i][j + 1]:
            i += 1
        else:
            j += 1
    return pares


def compara(gabarito: list[dict], emitidos: list[dict]) -> list[dict]:
    """Alinha as duas listas e classifica cada acontecimento.

    Devolve uma lista em ordem, com `situacao` em:
    `acerto`, `carta_errada`, `perdido`, `fantasma`.
    """
    pares = _subsequencia_comum(gabarito, emitidos)
    casados_g = {i for i, _ in pares}
    casados_e = {j for _, j in pares}

    # fronteiras dos buracos: entre um par casado e o próximo
    saida: list[dict] = []
    ig = ie = 0
    for pg, pe in pares + [(len(gabarito), len(emitidos))]:
        buraco_g = [k for k in range(ig, pg) if k not in casados_g]
        buraco_e = [k for k in range(ie, pe) if k not in casados_e]
        # mesmo tipo, mesmo buraco = a mesma jogada lida com a carta errada
        for tipo in ("draw", "discard"):
            gs = [k for k in buraco_g if gabarito[k]["tipo"] == tipo]
            es = [k for k in buraco_e if emitidos[k]["tipo"] == tipo]
            for k_g, k_e in zip(gs, es):
                saida.append({"situacao": "carta_errada", "tipo": tipo,
                              "esperado": gabarito[k_g]["carta"],
                              "obtido": emitidos[k_e]["carta"],
                              "ts": emitidos[k_e].get("ts"),
                              "i": emitidos[k_e].get("i")})
                buraco_g.remove(k_g)
                buraco_e.remove(k_e)
        for k in buraco_g:
            saida.append({"situacao": "perdido", "tipo": gabarito[k]["tipo"],
                          "esperado": gabarito[k]["carta"], "obtido": None,
                          "ts": gabarito[k].get("ts"), "i": gabarito[k].get("i")})
        for k in buraco_e:
            saida.append({"situacao": "fantasma", "tipo": emitidos[k]["tipo"],
                          "esperado": None, "obtido": emitidos[k]["carta"],
                          "ts": emitidos[k].get("ts"), "i": emitidos[k].get("i")})
        if pg < len(gabarito):
            saida.append({"situacao": "acerto", "tipo": gabarito[pg]["tipo"],
                          "esperado": gabarito[pg]["carta"],
                          "obtido": emitidos[pe]["carta"],
                          "ts": emitidos[pe].get("ts"),
                          "i": emitidos[pe].get("i")})
        ig, ie = pg + 1, pe + 1
    return saida


def nota(gabarito: list[dict], emitidos: list[dict]) -> dict:
    """Percentual de acerto por tipo, no formato da meta de aceite."""
    detalhe = compara(gabarito, emitidos)
    out = {"detalhe": detalhe}
    for tipo, rotulo in (("draw", "compras"), ("discard", "descartes")):
        do_tipo = [d for d in detalhe if d["tipo"] == tipo]
        acertos = sum(1 for d in do_tipo if d["situacao"] == "acerto")
        errados = sum(1 for d in do_tipo if d["situacao"] == "carta_errada")
        perdidos = sum(1 for d in do_tipo if d["situacao"] == "perdido")
        fantasmas = sum(1 for d in do_tipo if d["situacao"] == "fantasma")
        reais = acertos + errados + perdidos
        out[rotulo] = {
            "jogadas_reais": reais,
            "acertos": acertos,
            "carta_errada": errados,
            "perdidos": perdidos,
            "fantasmas": fantasmas,
            "acerto": acertos / reais if reais else 0.0,
        }
    return out


META = {"compras": 0.90, "descartes": 0.95}


def imprime(res: dict, detalhar: bool = True):
    for rotulo in ("compras", "descartes"):
        r = res[rotulo]
        alvo = META[rotulo]
        selo = "OK " if r["acerto"] >= alvo else "NÃO"
        print(f"  {selo} {rotulo:10s} {r['acerto']:6.1%} "
              f"(meta {alvo:.0%})  "
              f"{r['acertos']}/{r['jogadas_reais']} jogadas · "
              f"{r['carta_errada']} carta errada · {r['perdidos']} perdidas · "
              f"{r['fantasmas']} fantasmas")
    if not detalhar:
        return
    problemas = [d for d in res["detalhe"] if d["situacao"] != "acerto"]
    if not problemas:
        print("  nenhum erro")
        return
    print(f"\n  {len(problemas)} problemas:")
    for d in problemas:
        ts = f"t={d['ts']:7.1f}s" if d.get("ts") is not None else " " * 11
        alvo = d["esperado"] or "—"
        obtido = d["obtido"] or "—"
        print(f"    {ts}  {d['situacao']:13s} {d['tipo']:8s} "
              f"esperado {alvo:4s} obtido {obtido}")
