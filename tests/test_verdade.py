"""O instrumento contra a mão VERDADEIRA (`app/verdade.py`).

O caso que ele existe para acertar é o que a métrica sem gabarito erra: o
MODELO lê uma carta errada por um instante, a tela segura a certa, e a
referência que vem do quadro cobra isso da tela. Aqui a referência é a mão
dita pelo operador, e esse instante não pode contar como erro.
"""

from collections import Counter

from app.config import config
from app.verdade import MARGEM_JOGADA, mao_em, mede_verdade
from tests.test_leitura import FPS, frame, leque

MAO = ["7C", "3D", "JS", "3D", "7H", "9S", "AS", "4C", "5D"]
ASSENTA = config.fan_min_appear + config.lock_frames + config.fan_window


def _gravacao(blocos):
    registros, i = [], 0
    for cartas, n in blocos:
        for _ in range(n):
            registros.append(frame(i, cartas))
            i += 1
    return registros


def _verdade(mao=MAO, jogadas=(), fixa=True):
    return {"mao_inicial": list(mao), "ordem_fixa": fixa,
            "jogadas": list(jogadas)}


def test_mao_em_segue_as_jogadas_e_para_na_ultima():
    jogadas = [{"tipo": "draw", "carta": "KS", "ts": 10.0},
               {"tipo": "discard", "carta": "5D", "ts": 20.0}]
    mao, trans = mao_em(5.0, MAO, jogadas)
    assert mao == Counter(MAO) and not trans
    mao, trans = mao_em(10.0 + MARGEM_JOGADA / 2, MAO, jogadas)
    assert mao["KS"] == 1 and trans
    mao, trans = mao_em(15.0, MAO, jogadas)
    assert mao["KS"] == 1 and mao["5D"] == 1 and not trans
    mao, trans = mao_em(20.0, MAO, jogadas)
    assert "5D" not in mao and trans
    # depois da última jogada o gabarito acabou: não há verdade
    assert mao_em(20.1, MAO, jogadas) is None
    # mão fixa: vale a gravação inteira
    assert mao_em(10_000.0, MAO, [])[0] == Counter(MAO)


def test_margem_ANTES_da_jogada_para_gabarito_com_instante_de_emissao():
    """11/08 e 12/08: o instante é o da EMISSÃO, que vem depois da jogada."""
    jogadas = [{"tipo": "draw", "carta": "KS", "ts": 10.0},
               {"tipo": "discard", "carta": "KS", "ts": 30.0}]
    assert not mao_em(8.5, MAO, jogadas)[1]
    assert mao_em(8.5, MAO, jogadas, margem_antes=2.0)[1]
    assert not mao_em(7.5, MAO, jogadas, margem_antes=2.0)[1]
    # a mão verdadeira em si não muda com a margem: só o frame sai da conta
    assert mao_em(8.5, MAO, jogadas, margem_antes=2.0)[0] == Counter(MAO)


def test_modelo_errando_UM_instante_nao_e_erro_da_tela():
    """O 5♦ lido como 3♦ por poucos frames: a tela segura a mão certa.

    A métrica sem gabarito cobraria a tela aqui (é o 17/09 17:43). Contra a mão
    verdadeira, todo frame depois de assentar tem a mão E a ordem certas.
    """
    errada = [c if c != "5D" else "3D" for c in MAO]
    registros = _gravacao([(leque(MAO), ASSENTA), (leque(errada), 5),
                           (leque(MAO), 40)])
    r = mede_verdade(registros, _verdade())
    assert r["frames"] == len(registros)
    assert r["frames"] - r["conjunto_ok"] <= ASSENTA   # só o começo, sem mão
    assert r["ordem_ok"] == r["conjunto_ok"]


def test_tela_com_a_carta_errada_E_erro():
    """O outro lado: o modelo lê 3♦ SEMPRE; a tela mostra 3♦ e é cobrada."""
    errada = [c if c != "5D" else "3D" for c in MAO]
    r = mede_verdade(_gravacao([(leque(errada), ASSENTA + 60)]), _verdade())
    assert r["conjunto_ok"] == 0
    assert r["por_carta_falta"]["5D"] > 0 and r["por_carta_sobra"]["3D"] > 0


def test_ordem_errada_com_a_mao_certa_e_cobrada_so_na_mao_fixa():
    trocada = MAO[:]
    trocada[0], trocada[-1] = trocada[-1], trocada[0]
    registros = _gravacao([(leque(trocada), ASSENTA + 60)])
    r = mede_verdade(registros, _verdade())
    assert r["conjunto_ok"] > 0 and r["ordem_ok"] == 0
    r = mede_verdade(registros, _verdade(fixa=False))
    assert r["ordem_n"] == 0 and not r["ordem_cobrada"]


def test_frame_sem_o_leque_no_quadro_nao_entra_na_conta():
    registros = _gravacao([(leque(MAO), ASSENTA + 30), ([], 100)])
    r = mede_verdade(registros, _verdade())
    assert r["frames"] == ASSENTA + 30


def test_transicao_depois_da_jogada_fica_fora():
    nova = MAO + ["KS"]
    ts = (ASSENTA + 30) / FPS
    jogadas = [{"tipo": "draw", "carta": "KS", "ts": ts},
               {"tipo": "discard", "carta": "KS", "ts": 10_000.0}]
    registros = _gravacao([(leque(MAO), ASSENTA + 30), (leque(nova), 90)])
    r = mede_verdade(registros, _verdade(jogadas=jogadas))
    assert r["transicao"] == round(MARGEM_JOGADA * FPS)
    # passada a margem, a tela já adotou a mão com o KS
    assert r["conjunto_ok"] >= r["frames"] - ASSENTA
