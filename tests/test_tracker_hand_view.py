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


def test_hand_view_preserves_physical_order():
    """A ordem recebida é a do leque (esquerda -> direita) e deve sobreviver.

    Antes o tracker reordenava por naipe e valor, e o painel mostrava a mão
    embaralhada em relação ao que o jogador segurava.
    """
    t = GameTracker()
    t.set_hand_display(cards("KC", "AS", "10H", "2S", "AH"))
    codes = [card["code"] for card in t.state()["hand"]]
    assert codes == ["KC", "AS", "10H", "2S", "AH"]


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


def test_identical_hand_does_not_refire_on_change():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.set_hand_display(cards("AS", "2S"))
    t.set_hand_display(cards("AS", "2S"))
    assert calls == [1]


def test_reorder_is_a_change():
    # o jogador reorganizou o leque: a mão exibida tem de acompanhar
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.set_hand_display(cards("AS", "2S"))
    t.set_hand_display(cards("2S", "AS"))
    assert calls == [1, 1]
    assert [c.code for c in t.hand_view] == ["2S", "AS"]


def test_correct_hand_card_does_not_reorder():
    t = GameTracker()
    t.set_hand_display(cards("KC", "AS", "10H"))
    assert t.correct_hand_card(0, c("QC")) is True
    assert [x.code for x in t.hand_view] == ["QC", "AS", "10H"]
