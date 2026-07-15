from app.cards import Card
from app.detector import Detection, hand_codes, pick_top_card


def det(code, conf):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(0, 0, 10, 10))


def test_pick_top_card_highest_confidence():
    dets = [det("QS", 0.80), det("7D", 0.95), det("2C", 0.85)]
    assert pick_top_card(dets).card.code == "7D"


def test_pick_top_card_empty():
    assert pick_top_card([]) is None


def test_hand_codes_dedupes_corner_detections():
    # YOLO detecta os 2 cantos da mesma carta -> 2 detecções, 1 carta
    dets = [det("QS", 0.9), det("QS", 0.8), det("7D", 0.9)]
    assert hand_codes(dets) == frozenset({"QS", "7D"})
