from app.cards import Card
from app.detector import Detection
from app.hand_reader import FanReader


def d(code, x, y=100, size=30, conf=0.9):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, y, x + size, y + size))


def fan(*items):
    return [d(code, x) for code, x in items]


def test_confidence_outweighs_frequency_on_same_slot():
    """Naipe da mesma cor lido errado em confiança baixa não deve vencer.

    Padrão medido no setup real: o K♠ correto sai a ~0.85 e o K♣ errado a
    ~0.34. Por maioria simples o errado venceria (6 votos contra 4).
    """
    r = FanReader(min_appear=3, window=20)
    for _ in range(6):
        r.update([d("KC", 100, conf=0.34)])
    for _ in range(4):
        r.update([d("KS", 100, conf=0.85)])
    assert r.cards == ["KS"]  # 4*0.85 = 3.40 > 6*0.34 = 2.04


def test_plain_majority_still_wins_at_equal_confidence():
    r = FanReader(min_appear=3, window=20)
    for _ in range(2):
        r.update([d("4S", 100, conf=0.8)])
    for _ in range(5):
        r.update([d("AS", 100, conf=0.8)])
    assert r.cards == ["AS"]


def test_stable_fan_confirmed_after_min_appear():
    r = FanReader(min_appear=3)
    frame = fan(("AS", 100), ("2H", 200), ("3D", 300))
    assert r.update(frame) is False   # 1ª aparição
    assert r.update(frame) is False   # 2ª
    assert r.update(frame) is True    # 3ª -> confirma
    assert r.cards == ["AS", "2H", "3D"]


def test_majority_vote_beats_occasional_misread():
    r = FanReader(min_appear=3, window=10)
    for _ in range(5):
        r.update(fan(("AS", 100)))
    r.update(fan(("4S", 100)))          # 1 leitura errada na mesma vaga
    for _ in range(3):
        r.update(fan(("AS", 100)))
    assert r.cards == ["AS"]            # maioria AS vence o 4S


def test_phantom_single_frame_not_shown():
    r = FanReader(min_appear=5)
    for _ in range(6):
        r.update(fan(("AS", 100), ("2H", 200)))
    r.update(fan(("AS", 100), ("2H", 200), ("6C", 800)))  # fantasma 1 frame
    assert "6C" not in r.cards
    assert r.cards == ["AS", "2H"]


def test_twins_distinct_positions_both_shown():
    r = FanReader(min_appear=2)
    frame = fan(("7H", 100), ("7H", 300))
    r.update(frame); r.update(frame)
    assert r.cards == ["7H", "7H"]


def test_brief_absence_freezes():
    # o modelo falha por alguns frames: a mão exibida não pode piscar
    r = FanReader(min_appear=2, expire=20)
    frame = fan(("AS", 100), ("2H", 200))
    r.update(frame); r.update(frame)
    for _ in range(19):
        assert r.update([]) is False
    assert r.cards == ["AS", "2H"]


def test_prolonged_absence_empties_the_hand():
    # o jogador abaixou as cartas: a mão tem de sumir, não ficar congelada
    r = FanReader(min_appear=2, expire=20)
    frame = fan(("AS", 100), ("2H", 200))
    r.update(frame); r.update(frame)
    mudou = any(r.update([]) for _ in range(25))
    assert mudou is True
    assert r.cards == []


def test_hand_returning_after_emptying_is_read_again():
    r = FanReader(min_appear=2, expire=20)
    frame = fan(("AS", 100), ("2H", 200))
    r.update(frame); r.update(frame)
    for _ in range(25):
        r.update([])
    assert r.cards == []
    r.update(frame); r.update(frame)
    assert r.cards == ["AS", "2H"]


def test_removed_card_expires():
    r = FanReader(min_appear=2, expire=3)
    for _ in range(4):
        r.update(fan(("AS", 100), ("2H", 200)))
    for _ in range(4):                  # 2H some, AS continua
        r.update(fan(("AS", 100)))
    assert r.cards == ["AS"]


def test_cards_sorted_left_to_right():
    r = FanReader(min_appear=1)
    r.update(fan(("3D", 300), ("AS", 100), ("2H", 200)))
    assert r.cards == ["AS", "2H", "3D"]


def test_max_slots_caps_the_hand():
    r = FanReader(min_appear=2, max_slots=3)
    frame = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400))
    r.update(frame); r.update(frame)
    assert len(r.cards) == 3


def test_max_slots_keeps_recent_over_stale_after_fan_moves():
    """Leque se move: vaga velha é forte mas ausente; a nova é que vale."""
    r = FanReader(match_dist=30, min_appear=2, expire=24, max_slots=2)
    for _ in range(10):                       # posições antigas, bem firmadas
        r.update(fan(("AS", 100), ("2H", 200)))
    for _ in range(3):                        # leque desloca 200px à direita
        r.update(fan(("AS", 300), ("2H", 400)))
    assert r.cards == ["AS", "2H"]            # 2 vagas, não 4 duplicadas


def test_max_slots_drops_the_weakest_when_all_present():
    r = FanReader(min_appear=2, max_slots=2)
    for _ in range(5):
        r.update([d("AS", 100, conf=0.9), d("2H", 200, conf=0.9),
                  d("6C", 300, conf=0.31)])   # vaga fraca perde o corte
    assert r.cards == ["AS", "2H"]


def test_fan_translation_does_not_duplicate_slots():
    """A mão desloca o leque INTEIRO: as vagas acompanham em vez de duplicar.

    Sem compensação, um salto maior que `match_dist` cria vaga nova para cada
    carta e as antigas ainda vivem até `expire` — a mão aparecia com o dobro
    de cartas. Medido no setup real, o tremor da mão (66px p95) supera com
    folga o raio de casamento, então isso acontecia o tempo todo.
    """
    r = FanReader(match_dist=30, min_appear=2, expire=24)
    for _ in range(6):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300)))
    assert r.cards == ["AS", "2H", "3D"]
    for _ in range(4):                      # leque salta 80px (> match_dist)
        r.update(fan(("AS", 180), ("2H", 280), ("3D", 380)))
    assert r.cards == ["AS", "2H", "3D"]    # 3 vagas, não 6


def test_translation_preserves_the_accumulated_votes():
    # a vaga que se desloca continua sendo a MESMA vaga: leva os votos junto
    r = FanReader(match_dist=30, min_appear=5, expire=24)
    for _ in range(5):
        r.update(fan(("AS", 100), ("2H", 200)))
    assert r.cards == ["AS", "2H"]
    r.update(fan(("AS", 190), ("2H", 290)))   # salto de 90px num frame só
    assert r.cards == ["AS", "2H"]            # confirmadas na hora, sem re-acumular


def test_stray_detection_does_not_drag_the_slots():
    # um fantasma longe não pode arrastar o leque parado
    r = FanReader(match_dist=30, min_appear=2, expire=24)
    for _ in range(6):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300)))
    for _ in range(3):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300), ("KC", 900)))
    assert r.cards[:3] == ["AS", "2H", "3D"]


def test_shift_needs_support_from_several_slots():
    # uma deteccao isolada nao e evidencia de que o leque andou
    r = FanReader(match_dist=30, min_appear=2, expire=24)
    for _ in range(6):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400)))
    r.update(fan(("KC", 150)))              # frame ruim: 1 detecção só
    for _ in range(3):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400)))
    assert r.cards == ["AS", "2H", "3D", "4C"]


def test_established_label_survives_a_burst_of_misreads():
    """Camera tremendo: alguns frames borrados nao podem virar o rotulo.

    Sem histerese, uma rajada curta de leitura errada trocava a carta exibida
    por uma que nem esta no leque - e a mudanca ainda gerava compra e descarte
    fantasmas, porque os eventos saem da mudanca da mao.
    """
    r = FanReader(min_appear=3, window=30, win_margin=1.6)
    for _ in range(15):
        r.update([d("AS", 100, conf=0.85)])
    assert r.cards == ["AS"]
    for _ in range(4):                      # rajada de erro com confianca alta
        r.update([d("4S", 100, conf=0.90)])
    assert r.cards == ["AS"]                # nao ganhou por margem: segura


def test_a_real_change_still_wins_when_sustained():
    # a carta REALMENTE mudou: com votos sustentados, a nova assume
    r = FanReader(min_appear=3, window=30, win_margin=1.6)
    for _ in range(10):
        r.update([d("AS", 100, conf=0.85)])
    for _ in range(30):
        r.update([d("4S", 100, conf=0.85)])
    assert r.cards == ["4S"]


def test_closing_the_fan_does_not_scramble_the_hand():
    """Fechar o leque esconde as cartas atras da primeira - e oclusao.

    Sem congelar, as 8 vagas ocultas expiravam; ao reabrir nasciam sem
    historico de votos e o leitor podia estabelecer rotulo errado do zero,
    "esquecendo" o que ja tinha acertado.
    """
    r = FanReader(min_appear=3, expire=20, window=30)
    aberto = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400),
                 ("5S", 500))
    for _ in range(15):
        r.update(aberto)
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]

    fechado = fan(("AS", 100))          # so a primeira carta aparece
    for _ in range(60):                 # bem mais que `expire`
        r.update(fechado)
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]   # segurou

    for _ in range(3):                  # reabriu: volta na hora
        r.update(aberto)
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]


def test_one_card_leaving_is_still_a_real_change():
    # a regra do congelamento nao pode engolir a jogada legitima
    r = FanReader(min_appear=3, expire=6, window=30)
    cinco = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400),
                ("5S", 500))
    for _ in range(15):
        r.update(cinco)
    quatro = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400))
    for _ in range(15):
        r.update(quatro)
    assert r.cards == ["AS", "2H", "3D", "4C"]


def test_reopening_after_inserting_a_card_reads_the_new_card():
    """Fechar o leque com as DUAS maos, encaixar a compra e reabrir.

    E o gesto real do jogador: para por a carta comprada no meio do leque ele
    fecha, encaixa e reabre. Ao reabrir, as cartas NAO voltam para os lugares
    de antes - o leque foi remontado e tudo deslizou.

    Sem tratamento, as vagas guardadas durante a oclusao descrevem o leque
    ANTIGO: cada uma chega com 30 votos acumulados do rotulo velho e ainda tem
    a margem de histerese, entao a carta que passou a ocupar aquele lugar nao
    consegue derrubar o rotulo. A mao sai remontada nas posicoes erradas, e a
    "carta nova" que o tracker deduz do diff e qualquer uma - menos a certa.
    """
    r = FanReader(min_appear=3, expire=20, window=30)
    aberto = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400),
                 ("5S", 500))
    for _ in range(15):
        r.update(aberto)
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]

    for _ in range(40):                 # leque fechado por bem mais que expire
        r.update(fan(("AS", 100)))

    # reabriu com a KD encaixada no meio e o leque inteiro reposicionado
    remontado = fan(("AS", 100), ("2H", 180), ("KD", 260), ("3D", 340),
                    ("4C", 420), ("5S", 500))
    for _ in range(15):
        r.update(remontado)
    assert r.cards == ["AS", "2H", "KD", "3D", "4C", "5S"]


def test_brief_occlusion_still_preserves_the_votes():
    """A mao passando na frente NAO pode custar o historico de votos.

    O outro lado da moeda do teste acima: oclusao curta nao mexe no leque, e
    preservar os votos e o que faz a leitura certa voltar no primeiro frame.
    """
    r = FanReader(min_appear=8, expire=20, window=30)
    aberto = fan(("AS", 100), ("2H", 200), ("3D", 300), ("4C", 400),
                 ("5S", 500))
    for _ in range(15):
        r.update(aberto)

    for _ in range(5):                  # bem menos que expire
        r.update(fan(("AS", 100)))

    r.update(aberto)                    # UM frame e a mao ja esta de volta
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]


def test_squeezed_card_gets_its_own_slot():
    """Carta encaixada colada na vizinha nao pode dividir a vaga com ela.

    Medido ao vivo: com o 7C e o 9S sobrepostos, a vaga acumulava os dois
    rotulos num empate tecnico (9S=13.86 contra 7C=13.34) e a perdedora sumia
    da mao. O leitor entregava 9 cartas onde havia 10, e o tracker via "entrou
    uma e saiu outra" - que ele ignora de proposito. A compra nunca registrava.
    """
    r = FanReader(min_appear=3, expire=20, window=30)
    for _ in range(15):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300)))
    assert r.cards == ["AS", "2H", "3D"]

    # KD encaixada a 30px da 2H: dentro do raio de casamento (45) da vaga dela
    apertado = fan(("AS", 100), ("2H", 200), ("KD", 230), ("3D", 300))
    for _ in range(15):
        r.update(apertado)
    assert r.cards == ["AS", "2H", "KD", "3D"]


def test_same_corner_read_twice_does_not_duplicate_the_card():
    """O outro lado da regra de uma-por-vaga: MESMO rotulo colado = mesma carta.

    Medido ao vivo: o AS saiu numa vaga a 42px da propria, com confianca 0.55
    contra 0.94 da leitura boa - perto o bastante para disputar a vaga, longe o
    bastante para escapar da fusao do hand_instances (~15px). Tratada como
    "carta a mais", ela duplicava o as na mao exibida e gerava compra e
    descarte fantasmas do proprio as.
    """
    r = FanReader(min_appear=3, expire=20, window=30)
    for _ in range(15):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300)))
    assert r.cards == ["AS", "2H", "3D"]

    # segunda leitura do MESMO canto, 42px abaixo e menos confiante
    fantasma = [d("AS", 100), d("2H", 200), d("3D", 300),
                d("AS", 100, y=142, conf=0.55)]
    for _ in range(15):
        r.update(fantasma)
    assert r.cards == ["AS", "2H", "3D"]


def test_two_close_slots_with_the_same_label_are_merged():
    """A brecha da regra de uma-por-vaga: vagas gemeas JA estabelecidas.

    Aquela regra descarta a leitura repetida quando as duas DISPUTAM a mesma
    vaga. Se as duas vagas ja existem - cada deteccao casando com a sua - nao ha
    disputa e a duplicata se perpetua. Medido ao vivo: o AH ficou em duas vagas
    a 48px uma da outra (pesos 19.77 e 4.66), a mao saiu com dois ases de copas
    e o tracker emitiu compra fantasma do proprio as.
    """
    r = FanReader(min_appear=3, expire=20, window=30, match_dist=50)
    # as duas nascem JUNTAS, a 48px: cada deteccao casa com a sua vaga e a
    # regra de uma-por-vaga nunca chega a ser acionada
    for _ in range(15):
        r.update([d("AS", 100), d("AS", 148), d("2H", 400)])
    assert r.cards == ["AS", "2H"]


def test_twins_far_apart_survive_the_merge():
    """Gemeas dos 2 baralhos nao podem ser fundidas.

    Cantos vizinhos num leque real ficam a 44-111px (p05 = 69), acima do
    match_dist - a fusao so alcanca o que ja cairia na mesma vaga.
    """
    r = FanReader(min_appear=3, expire=20, window=30, match_dist=50)
    for _ in range(15):
        r.update([d("7H", 100), d("7H", 300), d("2S", 500)])
    assert r.cards == ["7H", "7H", "2S"]


def test_the_closest_detection_keeps_the_slot_whatever_the_order():
    """A disputa pela vaga se resolve por DISTANCIA, nao pela ordem da lista.

    Se valesse a primeira da lista, o resultado dependeria da ordem em que o
    modelo devolveu as caixas - e a carta legitima podia perder a propria vaga,
    com os votos acumulados dela, para a intrusa que chegou colada.
    """
    r = FanReader(min_appear=3, expire=20, window=30)
    for _ in range(15):
        r.update(fan(("AS", 100), ("2H", 200), ("3D", 300)))

    # a intrusa vem ANTES da dona da vaga na lista de deteccoes
    apertado = fan(("AS", 100), ("KD", 230), ("2H", 200), ("3D", 300))
    for _ in range(15):
        r.update(apertado)
    assert r.cards == ["AS", "2H", "KD", "3D"]


def test_reset_clears():
    r = FanReader(min_appear=1)
    r.update(fan(("AS", 100)))
    r.reset()
    assert r.cards == []


# --- zona morta da borda do quadro -------------------------------------------
#
# Medido na partida de 2026-08-11: uma carta que desce abaixo do enquadramento
# chega ao modelo com o índice AMPUTADO (caixa com y2 exatamente na altura do
# frame), e ele palpita sobre meio glifo — confiança mediana 0.43 contra 0.93
# das cartas inteiras. Nessa partida isso gerou um 4♦ que nunca existiu, e o
# 4♦ rendeu QUATRO eventos falsos (compra, descarte, compra do lixo, descarte).
#
# O teto de vagas não barra esse caso: numa mão de 9, a vaga espúria é a
# décima — exatamente a que o teto `hand_size + 1` existe para PERMITIR, para
# o instante da compra.

QUADRO = {"frame_w": 1920, "frame_h": 1080, "borda": 8}


def test_deteccao_cortada_pela_borda_nao_cria_vaga():
    r = FanReader(min_appear=3, window=20, max_slots=10, **QUADRO)
    for _ in range(30):
        r.update([d("AS", 500), d("KH", 700),
                  # índice cortado pela borda de baixo: y2 == altura do frame
                  Detection(card=Card.from_label("4D"), confidence=0.43,
                            box=(1041, 999, 1134, 1080))])
    assert r.cards == ["AS", "KH"]


def test_carta_legitima_que_desliza_para_a_borda_mantem_a_vaga():
    """Votar numa vaga existente continua valendo na borda.

    Suprimir o voto mataria a vaga mais rápido — o problema OPOSTO, e que
    aconteceu na mesma partida com o 3♦: a carta saiu do quadro, não da mão,
    e o sistema emitiu um descarte que não houve.
    """
    r = FanReader(min_appear=3, window=20, expire=5, **QUADRO)
    for _ in range(10):
        r.update([d("AS", 500), d("KH", 700, y=900)])
    assert r.cards == ["AS", "KH"]
    # o K♥ DESLIZA até encostar na borda — passo curto, dentro do raio de
    # casamento, que é como uma carta de verdade se move entre frames
    for y in range(900, 1060, 20):
        for _ in range(3):
            r.update([d("AS", 500),
                      Detection(card=Card.from_label("KH"), confidence=0.5,
                                box=(700, y, 730, min(y + 30, 1080)))])
    assert r.cards == ["AS", "KH"]


def test_sem_quadro_configurado_a_borda_nao_faz_nada():
    """Compatibilidade: `borda=0` (padrão) preserva o comportamento antigo."""
    r = FanReader(min_appear=3, window=20)
    for _ in range(30):
        r.update([d("AS", 500),
                  Detection(card=Card.from_label("4D"), confidence=0.43,
                            box=(1041, 999, 1134, 1080))])
    assert sorted(r.cards) == ["4D", "AS"]


def test_carta_que_SALTA_para_a_borda_e_perdida_de_proposito():
    """O custo assumido da regra da borda, registrado para não surpreender.

    Se a carta aparecer na borda longe da vaga anterior (salto maior que
    `match_dist`), ela não casa e também não pode nascer — some da mão. É o
    preço de não deixar nascer carta em cima de índice amputado, e a medição
    da partida de 2026-08-11 diz que o preço vale: 4 dos 5 fantasmas morreram
    sem custar um único acerto.
    """
    r = FanReader(min_appear=3, window=20, expire=5, **QUADRO)
    for _ in range(10):
        r.update([d("AS", 500), d("KH", 700, y=100)])
    assert r.cards == ["AS", "KH"]
    for _ in range(10):
        r.update([d("AS", 500),      # salto de ~950px direto para a borda
                  Detection(card=Card.from_label("KH"), confidence=0.5,
                            box=(700, 1050, 730, 1080))])
    assert r.cards == ["AS"]


def test_carta_duplicada_e_FRACA_nao_entra_na_mao():
    """O fantasma medido na partida de 12/08, em miniatura.

    O modelo lê o A♥ como A♦ por meio segundo. A vaga do A♥ ainda não expirou
    (é o que faz o leitor aguentar oclusão), então a mão sairia com A♥ MAIS
    dois A♦ — dez cartas que nunca estiveram juntas em frame nenhum. O tracker
    lê isso como carta que entrou, e sai uma compra que não aconteceu.

    A intrusa se denuncia por DUAS marcas juntas: duplica uma carta que já está
    na mão, e é muito mais fraca que as outras (medido ao vivo: 11,25 de
    confiança acumulada contra ~50 das vizinhas).
    """
    r = FanReader(min_appear=3, window=60, peso_min=0.6)
    firmes = fan(("AD", 100), ("AH", 300), ("9S", 500))
    for _ in range(40):
        r.update(firmes)
    assert r.cards == ["AD", "AH", "9S"]
    for _ in range(6):                      # rajada curta de leitura errada
        r.update(firmes + [d("AD", 380, conf=0.5)])
    assert r.cards == ["AD", "AH", "9S"]    # a segunda A♦ não vira carta


def test_gemea_LEGITIMA_sobrevive_ao_piso_de_peso():
    """Dois baralhos: carta repetida na mão é jogada válida, não erro.

    A diferença para o fantasma é o peso: a gêmea de verdade é vista tanto
    quanto as outras. Se o piso a derrubasse, ele estaria trocando um fantasma
    por uma carta perdida.
    """
    r = FanReader(min_appear=3, window=60, peso_min=0.6)
    leque = fan(("AD", 100), ("AD", 300), ("9S", 500))
    for _ in range(40):
        r.update(leque)
    assert r.cards == ["AD", "AD", "9S"]


def test_carta_COMPRADA_nasce_fraca_e_o_piso_nao_a_derruba():
    """Por que o piso só vale para rótulo DUPLICADO.

    Medido: um piso de peso sem essa condição derrubava a carta recém-comprada
    — ela também nasce fraca — e duas compras da partida de 11/08 passaram a
    sair com a carta errada. Quem entra na mão com rótulo NOVO é sempre carta,
    por mais fraca que esteja.
    """
    r = FanReader(min_appear=3, window=60, peso_min=0.6)
    for _ in range(40):
        r.update(fan(("AD", 100), ("AH", 300), ("9S", 500)))
    for _ in range(4):                      # a carta comprada acabou de entrar
        r.update(fan(("AD", 100), ("AH", 300), ("9S", 500), ("KC", 700)))
    assert r.cards == ["AD", "AH", "9S", "KC"]


def test_carta_na_OUTRA_MAO_nao_entra_no_leque():
    """O defeito que o usuario relatou ao testar o leitor rapido.

    Ele segurava 5 cartas numa mao e pegava a sexta com a outra; o leitor ja
    mostrava a carta solta como se estivesse no leque, antes de ele encaixar.

    O leque e uma CORRENTE de cartas que se encostam. A carta segurada a parte
    nao se liga a ninguem, e por isso cai — medido nas duas partidas gravadas,
    o vao dentro do leque fica em 0,7 largura de caixa (p99 = 1,3-1,9), e a
    carta separada esta muito alem disso.
    """
    r = FanReader(min_appear=3, window=30, vao_grupo=2.5)
    leque = [d(c, 100 + i * 60, size=40) for i, c in enumerate(
        ["AS", "2H", "3D", "4C", "5S"])]
    solta = d("KC", 900, size=40)             # na outra mao, longe do leque
    for _ in range(20):
        r.update(leque + [solta])
    assert r.cards == ["AS", "2H", "3D", "4C", "5S"]   # o KC nao entrou

    # agora ele ENCAIXA a carta no leque (aqui na ponta, para o teste medir a
    # entrada e nao a reacomodacao das outras vagas)
    encaixada = list(leque) + [d("KC", 100 + 5 * 60, size=40)]
    for _ in range(20):
        r.update(encaixada)
    assert r.cards == ["AS", "2H", "3D", "4C", "5S", "KC"]


def test_leque_inteiro_nao_e_partido_pelo_vao():
    """A regra nao pode cortar o proprio leque: so o que esta MUITO longe.

    Com o vao normal entre vizinhas (~0,7 largura), a corrente tem de
    sobreviver inteira — inclusive num leque bem aberto.
    """
    r = FanReader(min_appear=3, window=30, vao_grupo=2.5)
    # 40px de caixa, 80px de passo = 2,0 larguras: aberto, mas ainda leque
    leque = [d(c, 100 + i * 80, size=40) for i, c in enumerate(
        ["AS", "2H", "3D", "4C", "5S", "6H", "7D", "8C", "9S"])]
    for _ in range(20):
        r.update(leque)
    assert len(r.cards) == 9


def test_mao_exibida_inchada_nao_congela_o_leitor_para_sempre():
    """O congelamento por oclusao nao pode virar estado ABSORVENTE.

    Medido em 2026-08-20 numa partida gravada: a mao exibida inchou para 12
    cartas (vaga velha que ainda nao expirou somada a nova), o quadro passou a
    mostrar as 9 de verdade, e 9 < 12-1 em TODO frame. O leitor congelou por
    1.936 frames seguidos (~78 s) exibindo as 12, porque o codigo que reabre
    (`_occluded >= expire`) so roda num frame NAO congelado - que nunca chegou.
    A contradicao da partida ia a 50%.

    Ver 9 de 12 nao e oclusao: e um leque INTEIRO no quadro, e quem esta errada
    e a tela. Ver 1 de 9 (leque fechado) continua sendo oclusao - o teste
    `test_closing_the_fan_does_not_scramble_the_hand` guarda esse outro lado.
    """
    r = FanReader(min_appear=3, expire=6, window=30)
    codigos = ["AS", "2S", "3S", "4S", "5S", "6S", "7S", "8S", "9S",
               "10S", "JS", "QS"]
    doze = fan(*[(code, 100 + 60 * i) for i, code in enumerate(codigos)])
    for _ in range(10):
        r.update(doze)
    assert len(r.cards) == 12

    nove = doze[:9]                      # as tres ultimas sumiram de vez
    for _ in range(30):                  # bem mais que `expire`
        r.update(nove)
    assert r.cards == codigos[:9]        # a tela se corrigiu, nao travou
