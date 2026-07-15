from collections import Counter

from app.hand_view import HandView


def obs(**counts):
    return Counter(counts)


def test_card_enters_after_appear_frames():
    hv = HandView(appear_frames=3, absent_frames=5)
    assert hv.update(obs(QS=1)) is False
    assert hv.update(obs(QS=1)) is False
    assert hv.update(obs(QS=1)) is True
    assert hv.cards == ["QS"]


def test_twin_cards_both_counted():
    hv = HandView(appear_frames=2, absent_frames=5)
    hv.update(obs(**{"7H": 2, "9S": 1}))
    hv.update(obs(**{"7H": 2, "9S": 1}))
    assert sorted(hv.cards) == ["7H", "7H", "9S"]


def test_second_twin_appearing_later_increments():
    hv = HandView(appear_frames=2, absent_frames=5)
    hv.update(obs(**{"7H": 1}))
    hv.update(obs(**{"7H": 1}))
    assert hv.cards == ["7H"]
    hv.update(obs(**{"7H": 2}))
    hv.update(obs(**{"7H": 2}))
    assert hv.cards == ["7H", "7H"]


def test_flicker_does_not_enter():
    hv = HandView(appear_frames=3, absent_frames=5)
    hv.update(obs(QS=1))
    hv.update(obs())        # sumiu tudo: congela e zera candidatos
    hv.update(obs(QS=1))
    assert hv.update(obs(QS=1)) is False  # recomeçou a contagem
    assert hv.cards == []


def test_phantom_expires_while_others_visible():
    hv = HandView(appear_frames=2, absent_frames=3)
    hv.update(obs(QS=1, **{"4S": 1}))
    hv.update(obs(QS=1, **{"4S": 1}))
    assert sorted(hv.cards) == ["4S", "QS"]
    for _ in range(3):                   # 4S some, QS continua visível
        hv.update(obs(QS=1))
    assert hv.cards == ["QS"]


def test_twin_dropping_to_one_decrements():
    hv = HandView(appear_frames=2, absent_frames=3)
    hv.update(obs(**{"7H": 2}))
    hv.update(obs(**{"7H": 2}))
    for _ in range(3):
        hv.update(obs(**{"7H": 1}))
    assert hv.cards == ["7H"]


def test_lowered_hand_freezes_everything():
    hv = HandView(appear_frames=2, absent_frames=3)
    hv.update(obs(QS=1, **{"4S": 1}))
    hv.update(obs(QS=1, **{"4S": 1}))
    for _ in range(10):                  # mão fora do quadro
        assert hv.update(obs()) is False
    assert sorted(hv.cards) == ["4S", "QS"]


def test_absence_counter_resets_when_seen_again():
    hv = HandView(appear_frames=2, absent_frames=4)
    hv.update(obs(QS=1, **{"2H": 1}))
    hv.update(obs(QS=1, **{"2H": 1}))
    hv.update(obs(QS=1))                 # 2H ausente 1
    hv.update(obs(QS=1))                 # 2H ausente 2
    hv.update(obs(QS=1, **{"2H": 1}))    # 2H reapareceu: zera
    hv.update(obs(QS=1))
    hv.update(obs(QS=1))
    hv.update(obs(QS=1))
    assert "2H" in hv.cards              # 3 < 4 ausências consecutivas


def test_reset_clears_all():
    hv = HandView(appear_frames=1, absent_frames=2)
    hv.update(obs(QS=1))
    hv.reset()
    assert hv.cards == []
