from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def hand(*codes):
    return frozenset(c(x) for x in codes)


def test_partial_stable_set_updates_hand_view():
    t = GameTracker()
    t.on_stable_hand(hand("AS", "2S", "3S"))
    assert t.hand_view == hand("AS", "2S", "3S")
    assert t.events == []  # visão da mão não gera eventos


def test_hand_view_in_state_sorted_by_suit_then_rank():
    t = GameTracker()
    t.on_stable_hand(hand("KC", "AS", "10H", "2S", "AH"))
    codes = [card["code"] for card in t.state()["hand"]]
    assert codes == ["AS", "2S", "AH", "10H", "KC"]


def test_hand_view_replaced_by_new_stable_set():
    t = GameTracker()
    t.on_stable_hand(hand("AS", "2S"))
    t.on_stable_hand(hand("AS", "2S", "3S", "4S"))
    assert t.hand_view == hand("AS", "2S", "3S", "4S")


def test_new_round_clears_hand_view():
    t = GameTracker()
    t.on_stable_hand(hand("AS", "2S"))
    t.new_round()
    assert t.hand_view == frozenset()
    assert t.state()["hand"] == []


def test_paused_freezes_hand_view():
    t = GameTracker()
    t.on_stable_hand(hand("AS", "2S"))
    t.set_paused(True)
    t.on_stable_hand(hand("KC", "QC"))
    assert t.hand_view == hand("AS", "2S")


def test_on_change_fires_on_hand_view_update():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.on_stable_hand(hand("AS", "2S"))
    assert calls == [1]
