from app.cards import Card
from app.detector import (Detection, hand_card_instances, hand_codes,
                          pick_top_card)


def det(code, conf):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(0, 0, 10, 10))


def det_at(code, x, y, size=20, conf=0.9):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, y, x + size, y + size))


def test_pick_top_card_highest_confidence():
    dets = [det("QS", 0.80), det("7D", 0.95), det("2C", 0.85)]
    assert pick_top_card(dets).card.code == "7D"


def test_pick_top_card_empty():
    assert pick_top_card([]) is None


def test_hand_codes_dedupes_corner_detections():
    # YOLO detecta os 2 cantos da mesma carta -> 2 detecções, 1 carta
    dets = [det("QS", 0.9), det("QS", 0.8), det("7D", 0.9)]
    assert hand_codes(dets) == frozenset({"QS", "7D"})


def test_instances_vertical_pair_is_one_card():
    # canto de cima e canto de baixo da mesma carta em pé: dy >> dx
    dets = [det_at("7H", 100, 100), det_at("7H", 130, 300)]
    assert hand_card_instances(dets) == {"7H": 1}


def test_instances_side_by_side_are_twin_cards():
    # duas gêmeas no leque: cantos lado a lado (dx >> dy)
    dets = [det_at("7H", 100, 100), det_at("7H", 260, 110)]
    assert hand_card_instances(dets) == {"7H": 2}


def test_instances_overlapping_boxes_merge():
    # mesma detecção duplicada (caixas quase sobrepostas)
    dets = [det_at("7H", 100, 100), det_at("7H", 104, 102)]
    assert hand_card_instances(dets) == {"7H": 1}


def test_instances_single_detection_is_one():
    assert hand_card_instances([det_at("QS", 50, 50)]) == {"QS": 1}


def test_instances_different_labels_independent():
    dets = [det_at("7H", 100, 100), det_at("7D", 200, 100)]
    assert hand_card_instances(dets) == {"7H": 1, "7D": 1}


def test_vertical_pair_with_wrong_label_keeps_top():
    # canto de baixo (invertido) lido errado: A em cima, "4" embaixo
    dets = [det_at("AS", 100, 100), det_at("4S", 115, 280)]
    assert hand_card_instances(dets) == {"AS": 1}


def test_overlapping_different_labels_higher_confidence_wins():
    # mesmo canto com dois palpites: A (0.9) e 4 (0.6)
    dets = [det_at("AS", 100, 100, conf=0.9), det_at("4S", 103, 102, conf=0.6)]
    assert hand_card_instances(dets) == {"AS": 1}


def test_far_apart_boxes_not_paired_vertically():
    # verticais mas longe demais para serem a mesma carta (outra fileira)
    dets = [det_at("AS", 100, 100), det_at("4S", 110, 900)]
    assert hand_card_instances(dets) == {"AS": 1, "4S": 1}
