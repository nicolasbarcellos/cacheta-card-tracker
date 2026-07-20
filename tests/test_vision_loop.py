from app.cards import Card
from app.detector import Detection
from app.hand_reader import FanReader
from app.main import make_filters, process_frame
from app.stable_hand import StableHand
from app.tracker import GameTracker


def det(code, conf=0.9, x=0):
    # caixas espalhadas na horizontal como um leque real (posições distintas)
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, 0, x + 10, 10))


def hand(*codes):
    return [det(c, x=i * 100) for i, c in enumerate(codes)]

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]


def make_hand_view():
    return FanReader(match_dist=45, window=10, min_appear=3, expire=6)


def make_lock():
    return StableHand(hand_size=9, lock_frames=4)


def test_full_turn_emits_draw_then_discard():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv, lock = make_hand_view(), make_lock()

    for _ in range(3):
        process_frame([], hand(*HAND9), filters, tracker, hv, lock)
    assert tracker.events == []

    # compra: mão passa a ter 10 cartas estáveis
    for _ in range(3):
        process_frame([], hand(*HAND9, "KC"), filters, tracker, hv, lock)
    assert [e.type for e in tracker.events] == ["draw"]

    # descarte: QS aparece estável no lixo
    for _ in range(3):
        process_frame([det("QS")], hand(*HAND9, "KC"), filters, tracker,
                      hv, lock)
    assert [e.type for e in tracker.events] == ["draw", "discard"]


def test_locked_hand_shows_after_stable_nine():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv, lock = make_hand_view(), make_lock()
    for _ in range(15):  # 9 estáveis por tempo suficiente -> trava
        process_frame([], hand(*HAND9), filters, tracker, hv, lock)
    codes = [c["code"] for c in tracker.state()["hand"]]
    assert sorted(codes) == sorted(HAND9)


def test_locked_hand_holds_through_flicker():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv, lock = make_hand_view(), make_lock()
    for _ in range(15):
        process_frame([], hand(*HAND9), filters, tracker, hv, lock)
    eight = HAND9[:-1]
    for _ in range(10):  # a 9ª carta pisca (some/volta)
        process_frame([], hand(*eight), filters, tracker, hv, lock)
        process_frame([], hand(*HAND9), filters, tracker, hv, lock)
    codes = [c["code"] for c in tracker.state()["hand"]]
    assert sorted(codes) == sorted(HAND9)  # segurou as 9


def test_flicker_does_not_emit():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    hv, lock = make_hand_view(), make_lock()
    process_frame([det("QS")], [], filters, tracker, hv, lock)
    process_frame([], [], filters, tracker, hv, lock)
    process_frame([det("QS")], [], filters, tracker, hv, lock)
    assert tracker.events == []  # nunca ficou 3 frames estável
