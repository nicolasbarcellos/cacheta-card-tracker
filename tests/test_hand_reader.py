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


def test_reset_clears():
    r = FanReader(min_appear=1)
    r.update(fan(("AS", 100)))
    r.reset()
    assert r.cards == []
