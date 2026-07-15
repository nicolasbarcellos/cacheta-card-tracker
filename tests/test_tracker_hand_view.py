from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def hand(*codes):
    return tuple(c(x) for x in codes)


def test_partial_stable_set_updates_hand_view():
    t = GameTracker()
    t.on_stable_hand_instances(hand("AS", "2S", "3S"))
    assert t.hand_view == [c("AS"), c("2S"), c("3S")]
    assert t.events == []  # visão da mão não gera eventos


def test_duplicates_are_kept():
    # dois cantos/cartas com o mesmo rótulo aparecem duas vezes
    t = GameTracker()
    t.on_stable_hand_instances(hand("7H", "7H", "9S"))
    codes = [card["code"] for card in t.state()["hand"]]
    assert codes == ["9S", "7H", "7H"]


def test_hand_view_in_state_sorted_by_suit_then_rank():
    t = GameTracker()
    t.on_stable_hand_instances(hand("KC", "AS", "10H", "2S", "AH"))
    codes = [card["code"] for card in t.state()["hand"]]
    assert codes == ["AS", "2S", "AH", "10H", "KC"]


def test_hand_view_replaced_by_new_stable_set():
    t = GameTracker()
    t.on_stable_hand_instances(hand("AS", "2S"))
    t.on_stable_hand_instances(hand("AS", "2S", "3S", "4S"))
    assert len(t.hand_view) == 4


def test_new_round_clears_hand_view():
    t = GameTracker()
    t.on_stable_hand_instances(hand("AS", "2S"))
    t.new_round()
    assert t.hand_view == []
    assert t.state()["hand"] == []


def test_paused_freezes_hand_view():
    t = GameTracker()
    t.on_stable_hand_instances(hand("AS", "2S"))
    t.set_paused(True)
    t.on_stable_hand_instances(hand("KC", "QC"))
    assert t.hand_view == [c("AS"), c("2S")]


def test_on_change_fires_on_hand_view_update():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.on_stable_hand_instances(hand("AS", "2S"))
    assert calls == [1]


def test_partial_subset_does_not_shrink_hand():
    # abaixou a mão e levantou devagar: 5 das 9 visíveis não encolhem o leque
    t = GameTracker()
    nine = hand("AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D")
    t.on_stable_hand_instances(nine)
    t.on_stable_hand_instances(hand("AS", "2S", "3S", "4H", "5H"))
    assert len(t.hand_view) == 9


def test_set_with_new_card_replaces_hand():
    # carta nova no conjunto = mão realmente mudou (mesmo com menos cartas)
    t = GameTracker()
    t.on_stable_hand_instances(hand("AS", "2S", "3S"))
    t.on_stable_hand_instances(hand("AS", "KC"))
    assert t.hand_view == [c("AS"), c("KC")]


def test_full_hand_instances_still_drive_turn_logic():
    # a lógica de turno (compra) continua funcionando via instâncias
    t = GameTracker()
    nine = hand("AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D")
    t.on_stable_hand_instances(nine)
    t.on_stable_hand_instances(nine + hand("KC"))
    assert [e.type for e in t.events] == ["draw"]
    assert t.events[0].card == c("KC")
