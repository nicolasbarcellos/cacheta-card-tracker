from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def test_correct_event_replaces_card():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    event_id = t.events[0].id
    assert t.correct_event(event_id, c("QH")) is True
    assert t.events[0].card == c("QH")
    assert t.events[0].confirmed is True


def test_correct_discard_fixes_history():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.correct_event(t.events[0].id, c("QH"))
    t.on_stable_top_card(c("QS"))  # agora QS é um descarte novo de verdade
    assert [e.card.code for e in t.events] == ["QH", "QS"]


def test_correct_unknown_id_returns_false():
    t = GameTracker()
    assert t.correct_event(99, c("QS")) is False


def test_undo_removes_last_event():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    assert t.undo_last() is True
    assert t.events == []
    t.on_stable_top_card(c("QS"))  # pode ser detectado de novo
    assert len(t.events) == 1


def test_undo_empty_returns_false():
    assert GameTracker().undo_last() is False


def test_new_round_clears_state():
    t = GameTracker()
    hand = frozenset(Card.from_label(x) for x in
                     ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])
    t.on_stable_hand(hand)
    t.on_stable_top_card(c("QS"))
    t.new_round()
    assert t.events == []
    t.on_stable_top_card(c("QS"))  # rodada nova: QS pode ser descartada de novo
    assert len(t.events) == 1


def test_state_shape():
    t = GameTracker()
    hand = frozenset(Card.from_label(x) for x in
                     ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])
    t.on_stable_hand(hand)
    t.on_stable_hand(hand | {c("KC")})
    t.on_stable_top_card(c("QS"))
    s = t.state()
    assert s["draw"]["card"]["code"] == "KC"
    assert s["discard"]["card"]["code"] == "QS"
    assert s["paused"] is False
    assert len(s["events"]) == 2
    assert s["events"][0]["card"]["code"] == "QS"  # mais recente primeiro


def test_state_empty():
    s = GameTracker().state()
    assert s == {"draw": None, "discard": None, "paused": False, "events": []}
