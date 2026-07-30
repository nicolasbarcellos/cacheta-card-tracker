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


def test_lowered_hand_freezes():
    r = FanReader(min_appear=2)
    frame = fan(("AS", 100), ("2H", 200))
    r.update(frame); r.update(frame)
    for _ in range(30):
        assert r.update([]) is False    # sem detecções: congela
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


def test_reset_clears():
    r = FanReader(min_appear=1)
    r.update(fan(("AS", 100)))
    r.reset()
    assert r.cards == []
