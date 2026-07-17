from app.cards import Card
from app.detector import Detection
from app.hand_view import HandView
from app.main import make_filters, process_frame
from app.tracker import GameTracker


def det(code, conf=0.9, x=0):
    # caixas espalhadas na horizontal como um leque real (sobrepostas fundem)
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, 0, x + 10, 10))


def hand(*codes):
    return [det(c, x=i * 100) for i, c in enumerate(codes)]

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]


def make_hand_view():
    return HandView(appear_frames=3, absent_frames=6)


def test_full_turn_through_process_frame():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv = make_hand_view()

    # mão inicial estável (3 frames)
    for _ in range(3):
        process_frame([], hand(*HAND9), filters, tracker, hv)
    assert tracker.events == []
    assert len(tracker.hand_view) == 9  # mão exibida preenchida

    # compra: mão passa a ter 10 cartas estáveis
    for _ in range(3):
        process_frame([], hand(*HAND9, "KC"), filters, tracker, hv)
    assert [e.type for e in tracker.events] == ["draw"]
    assert len(tracker.hand_view) == 10

    # descarte: QS aparece estável no lixo
    for _ in range(3):
        process_frame([det("QS")], hand(*HAND9, "KC"), filters, tracker, hv)
    assert [e.type for e in tracker.events] == ["draw", "discard"]


def test_flicker_does_not_emit():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv = make_hand_view()
    process_frame([det("QS")], [], filters, tracker, hv)
    process_frame([], [], filters, tracker, hv)      # sumiu (mão na frente)
    process_frame([det("QS")], [], filters, tracker, hv)
    assert tracker.events == []  # nunca ficou 3 frames estável


def test_phantom_card_expires_from_hand_display():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv = make_hand_view()
    for _ in range(3):  # fantasma 4S junto com a mão real
        process_frame([], hand(*HAND9, "4S"), filters, tracker, hv)
    assert len(tracker.hand_view) == 10
    for _ in range(6):  # fantasma some; mão real continua visível
        process_frame([], hand(*HAND9), filters, tracker, hv)
    assert len(tracker.hand_view) == 9
    codes = [card["code"] for card in tracker.state()["hand"]]
    assert "4S" not in codes


def test_lowered_hand_keeps_display():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv = make_hand_view()
    for _ in range(3):
        process_frame([], hand(*HAND9), filters, tracker, hv)
    for _ in range(20):  # abaixou a mão: nenhuma detecção
        process_frame([], [], filters, tracker, hv)
    assert len(tracker.hand_view) == 9
