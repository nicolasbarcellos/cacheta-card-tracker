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


def hand_card_instances(detections: list[Detection]) -> Counter:
    """Conta as cartas da mão lendo APENAS o canto superior de cada uma.

    O canto inferior fica de cabeça para baixo e o modelo o lê mal
    (A vira 4 etc.), então:
    1. cantos praticamente sobrepostos = dois palpites para o mesmo canto
       → fica o de maior confiança;
    2. dois cantos em relação vertical (um sobre o outro, à distância de
       uma carta) = canto de cima + canto de baixo da MESMA carta, ainda
       que os rótulos lidos sejam diferentes → fica só o de CIMA.
    Gêmeas dos 2 baralhos sobrevivem: no leque ficam lado a lado.
    """
    boxes = []
    for d in detections:
        x1, y1, x2, y2 = d.box
        size = max(x2 - x1, y2 - y1, 1)
        boxes.append((d.card.code, (x1 + x2) / 2, (y1 + y2) / 2, size,
                      d.confidence))

    # 1) sobrepostas (mesmo canto, qualquer rótulo): maior confiança vence
    boxes.sort(key=lambda b: -b[4])
    kept: list[tuple] = []
    for code, cx, cy, size, conf in boxes:
        for _, kx, ky, ksize, _ in kept:
            if abs(cx - kx) < ksize * 0.8 and abs(cy - ky) < ksize * 0.8:
                break
        else:
            kept.append((code, cx, cy, size, conf))

    # 2) relação vertical dentro do alcance de uma carta: descarta o de baixo
    dropped = set()
    for i in range(len(kept)):
        if i in dropped:
            continue
        _, ix, iy, isize, _ = kept[i]
        for j in range(i + 1, len(kept)):
            if j in dropped:
                continue
            _, jx, jy, jsize, _ = kept[j]
            dx, dy = abs(ix - jx), abs(iy - jy)
            reach = 12 * max(isize, jsize)  # ~diagonal de uma carta
            if dy > dx and (dx * dx + dy * dy) ** 0.5 < reach:
                dropped.add(j if jy > iy else i)
                if i in dropped:
                    break

    return Counter(kept[i][0] for i in range(len(kept)) if i not in dropped)


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
