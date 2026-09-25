"""Testes do veredito de enquadramento (código puro).

Os dois casos que importam vêm de gravações reais: a de 24/09, que reprovou
por 3 px de mediana, e a de 18/09 15:50, que passa. Se o limiar de `ALVO_MIN`
subir ou descer, um dos dois cai — que é o ponto.
"""
from app.enquadramento import (ALVO_MAX, ALVO_MIN, PEQUENO, alturas_no_modelo,
                               avalia)


def test_quadro_sem_carta_nao_e_enquadramento_bom():
    """Ausência de medida não pode sair como "OK".

    É o caso em que o operador acha que conferiu: o script roda, não acha
    carta, e um `ok=True` mandaria gravar 5 minutos sem nada conferido.
    """
    v = avalia([])
    assert not v.ok
    assert v.n == 0
    assert "nenhuma carta" in v.acao


def test_a_gravacao_de_24_09_reprova_por_indice_pequeno():
    """p50 de 97 px reprova: é o defeito que custou a gravação de 24/09.

    Três px abaixo do alvo, com cauda: a perda daquela gravação foi 5,53%
    contra 3,19% da de 18/09.
    """
    alturas = [64] * 10 + [97] * 10 + [105] * 10      # p10/p50/p90 de 24/09
    v = avalia(alturas)
    assert not v.ok
    assert "aproxime" in v.acao.lower()


def test_a_gravacao_de_18_09_com_indice_grande_passa():
    """p50 de 127 px é a gravação de melhor perda medida (3,48%)."""
    v = avalia([99] * 10 + [127] * 10 + [149] * 10)
    assert v.ok
    assert "OK" in v.acao


def test_indice_muito_pequeno_pede_APROXIMAR_com_enfase():
    """Abaixo de 80 px a perda dobra ou triplica em todas as gravações."""
    v = avalia([60] * 5 + [70] * 5)
    assert not v.ok
    assert "APROXIME" in v.acao


def test_indice_grande_demais_tambem_reprova():
    """Acima de 130 o dado NÃO sustenta "maior é melhor".

    Em 18/09 16:48 a faixa >=120 px perdeu 8,78%, pior que os 1,04% da faixa
    100-120 — e o modelo é preso à escala. Sem este teste, o veredito viraria
    um piso e mandaria aproximar sem limite.
    """
    v = avalia([150] * 10 + [170] * 10)
    assert not v.ok
    assert "afaste" in v.acao


def test_a_fracao_pequena_e_contexto_e_NAO_reprova_sozinha():
    """Cauda pequena com mediana no alvo continua aprovada.

    São três gravações (23%, 15%, 1%), amostra fina demais para virar limiar;
    quem decide é a mediana. Se a fração entrar no veredito, a gravação de
    18/09 16:48 (15% de cauda e a melhor perda) passa a reprovar.
    """
    alturas = [70] * 15 + [110] * 85       # 15% de cauda, mediana no alvo
    v = avalia(alturas)
    assert v.ok
    assert 0.14 < v.fracao_pequena < 0.16


def test_a_altura_e_medida_na_escala_do_MODELO_nao_do_quadro():
    """A conversão é o que impede de aprovar enquadramento ruim.

    O detector devolve px de um quadro de 1920 e o modelo vê 1280. Sem o
    fator 2/3, um índice de 145 px no quadro cru (que chega ao modelo com 97 e
    reprova) apareceria como 145 e passaria.
    """
    caixas = [(0.0, 0.0, 50.0, 145.5)]
    (altura,) = alturas_no_modelo(caixas, 1920.0)
    assert 96 < altura < 98
    assert not avalia([altura] * 10).ok
    # e a mesma caixa num quadro que JÁ é 1280 não sofre conversão
    (igual,) = alturas_no_modelo(caixas, 1280.0)
    assert igual == 145.5


def test_quadro_de_largura_invalida_nao_explode():
    """Vem de `img.shape` quando a câmera devolve quadro degenerado."""
    assert alturas_no_modelo([(0.0, 0.0, 10.0, 20.0)], 0.0) == []


def test_os_limites_do_alvo_sao_coerentes():
    assert PEQUENO < ALVO_MIN < ALVO_MAX
