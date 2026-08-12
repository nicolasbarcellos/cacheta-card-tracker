from app.scoring import compara, nota


def ev(tipo, carta, ts=0.0):
    return {"tipo": tipo, "carta": carta, "ts": ts, "i": 0}


TURNO = [ev("draw", "AS"), ev("discard", "2S"),
         ev("draw", "3S"), ev("discard", "4S"),
         ev("draw", "5S"), ev("discard", "6S")]


def test_partida_perfeita_da_cem_por_cento():
    r = nota(TURNO, list(TURNO))
    assert r["compras"]["acerto"] == 1.0
    assert r["descartes"]["acerto"] == 1.0
    assert r["compras"]["jogadas_reais"] == 3


def test_carta_errada_conta_como_jogada_real_e_derruba_o_acerto():
    """Ler o descarte errado não é "não houve descarte": a jogada existiu.

    Se contasse só como evento inválido, o denominador cairia junto e o acerto
    ficaria em 100% — o sistema seria premiado por errar.
    """
    emitidos = [ev("draw", "AS"), ev("discard", "7H")]
    r = nota(TURNO[:2], emitidos)
    assert r["descartes"] == {"jogadas_reais": 1, "acertos": 0,
                              "carta_errada": 1, "perdidos": 0,
                              "fantasmas": 0, "acerto": 0.0}
    assert r["compras"]["acerto"] == 1.0


def test_jogada_perdida_nao_desalinha_o_resto_da_partida():
    """O casamento é por subsequência, não posição a posição.

    Perder o 2º evento desloca todos os seguintes em uma posição. Uma
    comparação posicional marcaria a partida inteira como errada dali em
    diante e mediria o deslocamento em vez do acerto.
    """
    emitidos = [e for e in TURNO if e["carta"] != "2S"]
    r = nota(TURNO, emitidos)
    assert r["compras"]["acerto"] == 1.0            # as 3 compras seguem certas
    assert r["descartes"]["acertos"] == 2
    assert r["descartes"]["perdidos"] == 1
    assert r["descartes"]["jogadas_reais"] == 3


def test_fantasma_nao_reduz_o_acerto_mas_e_reportado():
    """Fantasma não é jogada real, então não entra no denominador.

    Continua sendo defeito — suja o overlay — e por isso sai na contagem
    própria em vez de sumir da medição.
    """
    emitidos = TURNO[:2] + [ev("discard", "9D")]
    r = nota(TURNO[:2], emitidos)
    assert r["descartes"]["acerto"] == 1.0
    assert r["descartes"]["fantasmas"] == 1
    assert r["descartes"]["jogadas_reais"] == 1


def test_evento_nenhum_e_zero_por_cento_e_nao_cem():
    """O caso degenerado que a definição existe para evitar.

    Um sistema que não emite nada acerta 0% das jogadas — se a conta fosse
    "corretos entre os emitidos", ele passaria na meta sem fazer nada.
    """
    r = nota(TURNO, [])
    assert r["compras"]["acerto"] == 0.0
    assert r["descartes"]["acerto"] == 0.0
    assert r["descartes"]["perdidos"] == 3


def test_detalhe_localiza_o_erro_no_tempo():
    emitidos = [ev("draw", "AS"), ev("discard", "7H", ts=12.5)]
    problemas = [d for d in compara(TURNO[:2], emitidos)
                 if d["situacao"] != "acerto"]
    assert len(problemas) == 1
    assert problemas[0]["esperado"] == "2S"
    assert problemas[0]["obtido"] == "7H"
    assert problemas[0]["ts"] == 12.5
