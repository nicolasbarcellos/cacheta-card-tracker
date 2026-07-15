from dataclasses import dataclass

import cv2

from app.cards import Card, InvalidCardLabel


@dataclass
class Detection:
    card: Card
    confidence: float
    box: tuple  # x1, y1, x2, y2


def pick_top_card(detections: list[Detection]) -> Detection | None:
    """Heurística p/ topo do lixo: a carta com maior confiança.

    A carta do topo é a mais visível; cartas soterradas aparecem como
    frestas com confiança menor. Ajustar aqui se o setup real mostrar outra coisa.
    """
    if not detections:
        return None
    return max(detections, key=lambda d: d.confidence)


def hand_codes(detections: list[Detection]) -> frozenset[str]:
    return frozenset(d.card.code for d in detections)


def draw_boxes(frame, detections: list[Detection]):
    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d.box
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, f"{d.card.code} {d.confidence:.2f}", (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


class CardDetector:
    def __init__(self, model_path: str, min_confidence: float):
        from ultralytics import YOLO  # import tardio: pesado
        self.model = YOLO(model_path)
        self.min_confidence = min_confidence

    def detect(self, frame) -> list[Detection]:
        results = self.model.predict(frame, conf=self.min_confidence,
                                     verbose=False)
        detections = []
        for box in results[0].boxes:
            label = self.model.names[int(box.cls)]
            try:
                card = Card.from_label(label)
            except InvalidCardLabel:
                continue  # classe fora do baralho (ex.: joker do dataset)
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            detections.append(Detection(card=card,
                                        confidence=float(box.conf),
                                        box=(x1, y1, x2, y2)))
        return detections
