from collections import Counter
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


def hand_instances(detections: list[Detection]) -> list[Detection]:
    """Uma detecção por POSIÇÃO (canto de carta), sem colapsar o leque.

    Num leque apertado cada carta mostra só um índice de canto, lado a
    lado. Regra única: duas detecções cujos centros estão praticamente no
    MESMO lugar são o mesmo canto (dois palpites) → fica a de maior
    confiança. Posições distintas = cartas distintas, mesmo com rótulo
    igual (gêmeas dos 2 baralhos sobrevivem). Nada de lógica de "canto de
    baixo": o modelo v2 já foi treinado para ler só o canto de cima.
    """
    ordered = sorted(detections, key=lambda d: -d.confidence)
    kept: list[Detection] = []
    for d in ordered:
        cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
        size = max(d.box[2] - d.box[0], d.box[3] - d.box[1], 1)
        dup = False
        for k in kept:
            kx, ky = (k.box[0] + k.box[2]) / 2, (k.box[1] + k.box[3]) / 2
            ksize = max(k.box[2] - k.box[0], k.box[3] - k.box[1], 1)
            thr = 0.55 * min(size, ksize)  # só funde quase-coincidentes
            if abs(cx - kx) < thr and abs(cy - ky) < thr:
                dup = True
                break
        if not dup:
            kept.append(d)
    return kept


def hand_card_instances(detections: list[Detection]) -> Counter:
    """Contagem código→quantidade das cartas distintas da mão."""
    return Counter(d.card.code for d in hand_instances(detections))


def draw_boxes(frame, detections: list[Detection]):
    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d.box
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, f"{d.card.code} {d.confidence:.2f}", (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


class CardDetector:
    def __init__(self, model_path: str, min_confidence: float,
                 imgsz: int = 640):
        from ultralytics import YOLO  # import tardio: pesado
        self.model = YOLO(model_path)
        self.min_confidence = min_confidence
        self.imgsz = imgsz

    def detect(self, frame) -> list[Detection]:
        # agnostic_nms: dois palpites sobrepostos de classes diferentes
        # (mesmo canto lido como A e como 4) viram um só, o mais confiante
        results = self.model.predict(frame, conf=self.min_confidence,
                                     imgsz=self.imgsz, agnostic_nms=True,
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
