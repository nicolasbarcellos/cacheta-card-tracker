from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def test_new_top_card_emits_discard():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    assert len(t.events) == 1
    assert t.events[0].type == "discard"
    assert t.events[0].card == c("QS")


def test_same_top_card_does_not_repeat():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.on_stable_top_card(c("QS"))
    assert len(t.events) == 1


def test_old_top_reappearing_is_not_a_new_discard():
    # alguém comprou o topo do lixo e a carta de baixo (descarte antigo) reapareceu
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.on_stable_top_card(c("7D"))
    t.on_stable_top_card(c("QS"))  # 7D saiu do lixo, QS reapareceu
    assert [e.card.code for e in t.events] == ["QS", "7D"]


def test_paused_ignores_detections():
    t = GameTracker()
    t.paused = True
    t.on_stable_top_card(c("QS"))
    assert t.events == []


def test_low_confidence_marks_unconfirmed():
    t = GameTracker()
    t.on_stable_top_card(c("QS"), confidence=0.78)
    assert t.events[0].confirmed is False


def test_on_change_called():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.on_stable_top_card(c("QS"))
    assert calls == [1]
