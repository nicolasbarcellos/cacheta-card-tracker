from app.cards import Card
from app.detector import Detection
from app.main import make_filters, process_frame
from app.tracker import GameTracker


def det(code, conf=0.9):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(0, 0, 10, 10))


def hand(*codes):
    return [det(c) for c in codes]

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]


def test_full_turn_through_process_frame():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)

    # mão inicial estável (3 frames)
    for _ in range(3):
        process_frame([], hand(*HAND9), filters, tracker)
    assert tracker.events == []

    # compra: mão passa a ter 10 cartas estáveis
    for _ in range(3):
        process_frame([], hand(*HAND9, "KC"), filters, tracker)
    assert [e.type for e in tracker.events] == ["draw"]

    # descarte: QS aparece estável no lixo
    for _ in range(3):
        process_frame([det("QS")], hand(*HAND9, "KC"), filters, tracker)
    assert [e.type for e in tracker.events] == ["draw", "discard"]


def test_flicker_does_not_emit():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    process_frame([det("QS")], [], filters, tracker)
    process_frame([], [], filters, tracker)          # sumiu (mão na frente)
    process_frame([det("QS")], [], filters, tracker)
    assert tracker.events == []  # nunca ficou 3 frames estável
