"""O instrumento da nota precisa de teste tanto quanto o pipeline.

Uma métrica errada é pior que métrica nenhuma: ela não avisa que está errada, e
todo parâmetro afinado contra ela fica afinado no ruído. Foi o que quase
aconteceu com a contradição — a primeira versão cobrava como defeito a carta
que o jogador segura à parte, que o leitor esconde DE PROPÓSITO desde
2026-08-19. É o `test_carta_segurada_a_parte_nao_conta_como_contradicao`.

Os frames aqui usam a geometria REAL do índice de canto (44x84, estreito e
alto), como em `tests/test_replay_fidelity.py`: caixa quadrada não exercita o
raio de fusão do `hand_instances`, que sai da MENOR dimensão.
"""

from app.config import config
from app.leitura import mede
from app.main import build_pipeline, process_frame
from app.replay import detections_do_registro
from app.tracker import GameTracker

FPS = 30.0
LARGURA = 44          # largura da caixa do índice
PASSO = 70            # espaçamento entre cantos vizinhos no leque (p05 real: 69)


def frame(i: int, cartas, conf: float = 0.9) -> dict:
    """Um registro de frame como o `SessionRecorder` grava.

    `cartas` são pares (código, x) — o x é o canto esquerdo da caixa, e é ele
    que define a ordem física do leque, da esquerda para a direita.
    """
    return {"t": "frame", "i": i, "ts": round(i / FPS, 3), "v": i,
            "dets": [[code, conf, x, 100, x + LARGURA, 184]
                     for code, x in cartas]}


def leque(codes, x0: int = 300, passo: int = PASSO):
    return [(code, x0 + n * passo) for n, code in enumerate(codes)]


def exibida_ao_fim(registros) -> list[str]:
    """A mão que ficou NA TELA ao fim da gravação sintética."""
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()
    for rec in registros:
        process_frame(detections_do_registro(rec, config.min_confidence),
                      tracker, leitor, trava, verbose=False)
    return list(trava.cards)


def partida(blocos) -> list[dict]:
    """Concatena (cartas, n_frames) numa gravação sintética."""
    registros, i = [], 0
    for cartas, n in blocos:
        for _ in range(n):
            registros.append(frame(i, cartas))
            i += 1
    return registros


# Quanto tempo o pipeline leva para assentar: a vaga precisa de `min_appear`
# votos, o StableHand precisa do score subir e ficar `lock_frames` estável.
# Derivado da config, nunca fixo — afinar esses valores é o que o replay existe
# para permitir, e não pode quebrar o teste do instrumento que os mede.
ASSENTA = config.fan_min_appear + config.lock_frames + config.fan_window


def test_atraso_e_o_tempo_entre_ver_a_carta_e_ela_chegar_na_tela():
    """A mão aparece na tela alguns frames DEPOIS de a leitura viva mostrá-la.

    O valor esperado não é zero nem arbitrário: a leitura viva só existe depois
    de `fan_min_appear` votos, e a tela só troca depois de `lock_frames` frames
    estáveis. O atraso medido tem de ser essa espera, em segundos.
    """
    res = mede(partida([(leque(["AS", "2S", "3S", "4H", "5H"]), ASSENTA)]))

    esperado = config.lock_frames / FPS
    assert res["atraso"]["n"] == 1
    # folga de 4 frames: o score do StableHand leva 2 frames para cruzar o
    # limiar de presença, e não é isso que o teste está fixando
    assert abs(res["atraso"]["mediana"] - esperado) <= 4 / FPS
    assert res["trocas"] == 1


def test_carta_segurada_a_parte_nao_conta_como_contradicao():
    """O comportamento PEDIDO não pode ser cobrado como defeito.

    O jogador pega a carta com a outra mão e a segura fora do leque enquanto
    decide onde encaixar. O leitor não a mostra (é o `_so_o_leque`), e ela fica
    visível no quadro com confiança alta — exatamente a assinatura de uma
    contradição. Cobrá-la mediria a feature como erro: na partida de 19/08 isso
    era a diferença entre 7,5% e 9,2%.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    # a carta à parte, bem longe do leque (o corte é em 2,5 larguras de caixa)
    a_parte = [("KC", mao[-1][1] + int(6 * LARGURA))]
    registros = partida([(mao + a_parte, ASSENTA)])

    res = mede(registros)
    assert res["com_mao"] > 0
    assert res["contradicao"]["frames"] == 0

    # CONTROLE: a carta à parte era perfeitamente legível o tempo todo — com o
    # corte desligado ela vira carta da mão. Sem esta metade, o teste acima
    # passaria também se a detecção fosse fraca demais para ser vista, e não
    # provaria nada sobre a regra do leque.
    antes = config.fan_vao_grupo
    try:
        config.fan_vao_grupo = 0.0
        assert "KC" in exibida_ao_fim(registros)
    finally:
        config.fan_vao_grupo = antes
    assert "KC" not in exibida_ao_fim(registros)


def test_contradicao_cobra_a_carta_que_o_quadro_mostra_e_a_tela_nao():
    """Carta nova no leque, visível e com confiança alta, ainda fora da tela.

    É o defeito que o jogador enxerga: ele já vê a carta na mão e a tela ainda
    mostra a mão de antes. Enquanto a troca não assenta, cada frame conta.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    nova = mao + [("KC", mao[-1][1] + PASSO)]      # encaixada NO leque
    res = mede(partida([(mao, ASSENTA), (nova, ASSENTA)]))

    assert res["contradicao"]["frames"] > 0
    assert dict(res["contradicao"]["por_carta"])["KC"] > 0
    assert res["trocas"] == 2


def test_contradicao_nao_cobra_leitura_de_confianca_baixa():
    """Abaixo do limiar, a divergência é ambígua — pode ser o modelo errando.

    Se a carta é lida com confiança baixa e não está na tela, não dá para dizer
    que a tela está errada; provavelmente é a leitura. Cobrar isso mediria erro
    de MODELO na conta da EXIBIÇÃO, que é o que este instrumento não faz.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    nova = mao + [("KC", mao[-1][1] + PASSO)]
    registros = partida([(mao, ASSENTA)]) + [
        {**frame(i, nova), "dets": [
            [code, 0.9 if code != "KC" else 0.4, x, 100, x + LARGURA, 184]
            for code, x in nova]}
        for i in range(ASSENTA, 2 * ASSENTA)]

    res = mede(registros, conf_alta=0.80)
    assert dict(res["contradicao"]["por_carta"]).get("KC") is None


def test_excesso_cobra_a_carta_que_ficou_na_tela_depois_de_sumir_do_quadro():
    """O espelho da contradição, e o número que faltava até 2026-08-20.

    Sem ele, um leitor que exibisse TUDO o que já viu tirava nota ótima — foi
    assim que 44,5% de frames exibindo 17 cartas passaram despercebidos.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    # o leque perde a última carta: some do QUADRO, e a tela demora a soltar
    menor = mao[:-1]
    res = mede(partida([(mao, ASSENTA), (menor, ASSENTA)]))

    assert res["excesso"]["frames"] > 0
    assert dict(res["excesso"]["por_carta"])["5H"] > 0


def test_excesso_com_o_leitor_congelado_sai_em_contagem_PROPRIA():
    """Segurar a mão durante a oclusão é o comportamento PEDIDO, não defeito.

    Com o leque fechado (ou o quadro vazio) o invariante do projeto é congelar
    o estado, não zerá-lo — e nesses frames a tela mostra, de propósito, carta
    que o quadro não está mostrando. Cobrar isso no total mediria a feature
    como erro, que é o que a contradição já fez com a carta segurada à parte.

    Medido nas gravações em 2026-08-24: 16-51% do excesso está neste estado.
    Fica publicado à parte em vez de descontado, pelo mesmo motivo que a
    cobertura e a atividade são dois números — mudar o denominador em silêncio
    esconde, publicar os dois deixa escolher. Quem diz que o leitor congelou é
    o LEITOR (`FanReader.congelado`), não uma cópia da regra dentro da métrica.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    # o leque FECHA: sobra uma carta só, bem abaixo da fração de oclusão
    fechado = mao[:1]
    res = mede(partida([(mao, ASSENTA), (fechado, ASSENTA)]))

    assert res["excesso"]["frames"] > 0
    assert res["excesso"]["congelado"] > 0
    # e a repartição fecha: o que sobra do congelado é o excesso "vivo"
    vivo = res["excesso"]["frames"] - res["excesso"]["congelado"]
    assert abs(res["excesso"]["pct_vivo"] - vivo / res["com_mao"]) < 1e-9
    assert res["excesso"]["pct_vivo"] <= res["excesso"]["pct"]


def test_ordem_certa_nao_conta_como_erro():
    """O leque parado e bem lido tem de dar 0% de ordem errada.

    A ordem só é comparada nos frames em que a tela tem as MESMAS cartas do
    quadro — quando as cartas divergem, o defeito é de conjunto e já é cobrado
    pela contradição. Contar de novo aqui cobraria o mesmo erro duas vezes.
    """
    res = mede(partida([(leque(["AS", "2S", "3S", "4H", "5H"]), ASSENTA)]))
    assert res["ordem"]["comparaveis"] > 0
    assert res["ordem"]["errada"] == 0


def test_cobertura_nao_cobra_o_tempo_sem_ninguem_na_frente_da_camera():
    """O denominador da cobertura é o que a torna útil ou enganosa.

    Metade desta gravação sintética não tem carta nenhuma no quadro — como as
    partidas reais de 19/08, em que o app ficou ligado sozinho por vários
    minutos. Cobrar isso do leitor daria 50% de cobertura e faria parecer que o
    leque vive fora do enquadramento; contando só os frames COM carta, a
    cobertura é alta e a ausência aparece na ATIVIDADE, onde ela pertence.
    """
    mao = leque(["AS", "2S", "3S", "4H", "5H"])
    registros = partida([([], ASSENTA), (mao, ASSENTA)])   # sem mão, depois com

    res = mede(registros)
    assert res["frames"] == 2 * ASSENTA
    assert res["atividade"] < 0.55            # metade da gravação é vazia
    assert res["cobertura"] > 0.6             # mas quando há carta, há tela
