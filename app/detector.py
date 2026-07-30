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


# Fração da MENOR dimensão da caixa usada como raio de fusão. A caixa de um
# índice de canto é estreita e ALTA (mediana medida: 44x84 px), e as cartas do
# leque se separam no eixo ESTREITO (horizontal): espaçamento entre cantos
# vizinhos de 19 px no pior caso, 34 px na mediana.
#
# Usando a MAIOR dimensão (como era antes) o raio dava 0.55*84 = 46 px, MAIOR
# que o espaçamento — cada carta apagava a vizinha como se fosse o mesmo canto
# lido duas vezes, e só 51,7% das cartas da mão sobreviviam. Pela menor
# dimensão sobem para 91,9%, e o resultado é IDÊNTICO para qualquer fator
# <= 0.45: a escolha está num platô, não numa borda.
#
# 0.35 é a ponta segura desse platô: dá raio de ~15 px, abaixo dos 19 px do
# pior espaçamento observado (com 0.45 o raio ficaria em 19,8 px e voltaria a
# fundir vizinhas no caso extremo), e ainda funde de sobra os dois palpites do
# MESMO canto, cujos centros ficam a poucos pixels um do outro.
MERGE_FACTOR = 0.35


def hand_instances(detections: list[Detection]) -> list[Detection]:
    """Uma detecção por POSIÇÃO (canto de carta), sem colapsar o leque.

    Num leque apertado cada carta mostra só um índice de canto, lado a
    lado. Regra única: duas detecções cujos centros estão praticamente no
    MESMO lugar são o mesmo canto (dois palpites) → fica a de maior
    confiança. Posições distintas = cartas distintas, mesmo com rótulo
    igual (gêmeas dos 2 baralhos sobrevivem). Nada de lógica de "canto de
    baixo": o modelo v2 já foi treinado para ler só o canto de cima.

    O raio de fusão sai da MENOR dimensão da caixa — ver MERGE_FACTOR.
    """
    ordered = sorted(detections, key=lambda d: -d.confidence)
    kept: list[Detection] = []
    for d in ordered:
        cx, cy = (d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2
        size = max(min(d.box[2] - d.box[0], d.box[3] - d.box[1]), 1)
        dup = False
        for k in kept:
            kx, ky = (k.box[0] + k.box[2]) / 2, (k.box[1] + k.box[3]) / 2
            ksize = max(min(k.box[2] - k.box[0], k.box[3] - k.box[1]), 1)
            thr = MERGE_FACTOR * min(size, ksize)  # só funde quase-coincidentes
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
                 imgsz: int = 640, agnostic_nms: bool = False):
        from ultralytics import YOLO  # import tardio: pesado
        self.model = YOLO(model_path)
        self.min_confidence = min_confidence
        self.imgsz = imgsz
        self.agnostic_nms = agnostic_nms

    def detect(self, frame) -> list[Detection]:
        # agnostic_nms fica DESLIGADO por padrão: fundir palpites de classes
        # diferentes aqui é decidir por frame e sem volta, e num leque apertado
        # também mata a carta vizinha. Quem decide é o FanReader, votando ao
        # longo do tempo. Ver o comentário em config.agnostic_nms.
        results = self.model.predict(frame, conf=self.min_confidence,
                                     imgsz=self.imgsz,
                                     agnostic_nms=self.agnostic_nms,
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
