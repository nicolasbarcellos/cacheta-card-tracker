from app.cards import Card
from app.tracker import GameTracker

HAND = frozenset(Card.from_label(x) for x in
                 ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])


def c(code):
    return Card.from_label(code)


def test_first_full_hand_sets_reference_without_event():
    t = GameTracker()
    t.on_stable_hand(HAND)
    assert t.events == []


def test_extra_card_emits_draw_from_monte():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(HAND | {c("KC")})
    assert len(t.events) == 1
    assert t.events[0].type == "draw"
    assert t.events[0].card == c("KC")
    assert t.events[0].source == "monte"


def test_draw_from_lixo_detected_by_history():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_top_card(c("KC"))       # alguém descartou KC no lixo
    t.on_stable_hand(HAND | {c("KC")})  # eu peguei o KC
    draws = [e for e in t.events if e.type == "draw"]
    assert draws[0].source == "lixo"


def test_card_taken_from_lixo_can_be_discarded_again():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_top_card(c("KC"))
    t.on_stable_hand(HAND | {c("KC")})  # comprei do lixo
    t.on_stable_top_card(c("KC"))       # e descartei o mesmo KC de volta
    discards = [e for e in t.events if e.type == "discard"]
    assert [e.card.code for e in discards] == ["KC", "KC"]


def test_nine_card_set_updates_reference():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(HAND | {c("KC")})            # comprou KC
    new_hand = frozenset(list(HAND)[1:]) | {c("KC")}  # descartou uma antiga
    t.on_stable_hand(new_hand)                     # mão volta a 9
    t.on_stable_hand(new_hand | {c("QC")})         # próximo turno: compra QC
    draws = [e for e in t.events if e.type == "draw"]
    assert [e.card.code for e in draws] == ["KC", "QC"]


def test_garbage_sets_are_ignored():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(frozenset([c("KC"), c("QC")]))  # detecção ruim (2 cartas)
    assert t.events == []
    t.on_stable_hand(HAND | {c("KC")})
    assert len(t.events) == 1  # referência não foi corrompida


def test_paused_ignores_hand():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.paused = True
    t.on_stable_hand(HAND | {c("KC")})
    assert t.events == []
