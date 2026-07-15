from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def cards(*codes):
    return [c(x) for x in codes]


def test_set_hand_display_updates_view():
    t = GameTracker()
    t.set_hand_display(cards("AS", "2S", "3S"))
    assert t.hand_view == cards("AS", "2S", "3S")
    assert t.events == []  # visão da mão não gera eventos


def test_hand_view_in_state_sorted_by_suit_then_rank():
    t = GameTracker()
    t.set_hand_display(cards("KC", "AS", "10H", "2S", "AH"))
    codes = [card["code"] for card in t.state()["hand"]]
    assert codes == ["AS", "2S", "AH", "10H", "KC"]


def test_new_round_clears_hand_view():
    t = GameTracker()
    t.set_hand_display(cards("AS", "2S"))
    t.new_round()
    assert t.hand_view == []
    assert t.state()["hand"] == []


def test_paused_freezes_hand_view():
    t = GameTracker()
    t.set_hand_display(cards("AS", "2S"))
    t.set_paused(True)
    t.set_hand_display(cards("KC", "QC"))
    assert t.hand_view == cards("AS", "2S")


def test_on_change_fires_on_hand_view_update():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.set_hand_display(cards("AS", "2S"))
    assert calls == [1]


def test_same_hand_does_not_refire_on_change():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.set_hand_display(cards("AS", "2S"))
    t.set_hand_display(cards("2S", "AS"))  # mesma mão, outra ordem
    assert calls == [1]
