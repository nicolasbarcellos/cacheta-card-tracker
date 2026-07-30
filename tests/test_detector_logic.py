from app.cards import Card
from app.detector import (Detection, hand_card_instances, hand_codes,
                          hand_instances, pick_top_card)


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


def test_instances_side_by_side_are_twin_cards():
    # duas gêmeas no leque: cantos lado a lado, posições distintas
    dets = [det_at("7H", 100, 100), det_at("7H", 260, 110)]
    assert hand_card_instances(dets) == {"7H": 2}


def test_instances_overlapping_boxes_merge():
    # mesma detecção duplicada (caixas quase coincidentes) -> 1
    dets = [det_at("7H", 100, 100), det_at("7H", 104, 102)]
    assert hand_card_instances(dets) == {"7H": 1}


def test_instances_single_detection_is_one():
    assert hand_card_instances([det_at("QS", 50, 50)]) == {"QS": 1}


def test_instances_different_labels_independent():
    dets = [det_at("7H", 100, 100), det_at("7D", 200, 100)]
    assert hand_card_instances(dets) == {"7H": 1, "7D": 1}


def test_overlapping_different_labels_higher_confidence_wins():
    # mesmo canto com dois palpites: A (0.9) e 4 (0.6) quase coincidentes
    dets = [det_at("AS", 100, 100, conf=0.9), det_at("4S", 103, 102, conf=0.6)]
    assert hand_card_instances(dets) == {"AS": 1}


def det_tall(code, x, y, w=44, h=84, conf=0.9):
    """Caixa com a forma REAL de um índice de canto: estreita e alta."""
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, y, x + w, y + h))


def test_tall_index_boxes_at_fan_spacing_are_not_merged():
    """Regressão: o raio de fusão vinha da MAIOR dimensão (a altura).

    Com a caixa real (44x84px) isso dava 46px de raio, maior que o
    espaçamento entre cantos vizinhos (19px no pior caso, 34px mediano), e
    cada carta apagava a vizinha — 48% da mão desaparecia. O raio tem de sair
    da menor dimensão (a largura), que é o eixo em que o leque se separa.
    """
    dets = [det_tall("AS", 100, 100), det_tall("2H", 134, 103),
            det_tall("3D", 168, 106)]
    assert len(hand_instances(dets)) == 3


def test_tall_index_boxes_worst_case_spacing_survives():
    # 19px é o menor espaçamento medido entre cantos vizinhos
    dets = [det_tall("AS", 100, 100), det_tall("2H", 119, 101)]
    assert len(hand_instances(dets)) == 2


def test_tall_index_same_corner_two_guesses_still_merges():
    # mesmo canto lido como A e como 4: centros quase coincidentes -> funde
    dets = [det_tall("AS", 100, 100, conf=0.9),
            det_tall("4S", 104, 103, conf=0.6)]
    kept = hand_instances(dets)
    assert len(kept) == 1
    assert kept[0].card.code == "AS"


def test_tight_fan_nine_distinct_corners_not_collapsed():
    # leque apertado: 9 cantos numa fileira, próximos mas distintos -> 9
    codes = ["AS", "2H", "3D", "4C", "5S", "6H", "7D", "8C", "9S"]
    dets = [det_at(c, 100 + i * 45, 100 + i * 3) for i, c in enumerate(codes)]
    result = hand_card_instances(dets)
    assert sum(result.values()) == 9
    assert set(result) == set(codes)
