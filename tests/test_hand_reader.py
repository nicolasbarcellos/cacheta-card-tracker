from app.cards import Card
from app.detector import Detection
from app.hand_reader import FanReader


def d(code, x, y=100, size=30):
    return Detection(card=Card.from_label(code), confidence=0.9,
                     box=(x, y, x + size, y + size))


def fan(*items):
    return [d(code, x) for code, x in items]


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


def test_reset_clears():
    r = FanReader(min_appear=1)
    r.update(fan(("AS", 100)))
    r.reset()
    assert r.cards == []
