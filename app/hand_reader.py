from collections import Counter, deque


class FanReader:
    """Lê o leque com votação temporal por posição ("vaga").

    Cada carta do leque ocupa uma posição estável na imagem. A cada frame,
    as detecções são casadas a vagas pela proximidade; cada vaga acumula os
    rótulos vistos numa janela recente e exibe o MAIS VOTADO — com o voto
    PONDERADO PELA CONFIANÇA. Medido no setup real: quando o modelo erra o
    naipe dentro da mesma cor (♠↔♣, ♥↔♦) ele o faz com confiança ~0.34,
    enquanto acerta com ~0.85; somar confiança em vez de contar cabeças faz
    o rótulo certo vencer mesmo aparecendo em menos frames. Isso:
    - estabiliza (o rótulo certo, maioria, vence as leituras erradas);
    - mata fantasmas (detecção esporádica não atinge o mínimo de aparições);
    - preserva gêmeas (posições distintas = vagas distintas);
    - some quando a mão abaixa (vagas expiram por ausência).

    `max_slots` (= tamanho da mão) é o teto de vagas exibidas. Ele existe
    porque a mão tem um número conhecido de cartas: se sobrar vaga, alguma é
    espúria. Sem o teto era preciso um `expire` curto para matar vaga órfã
    (leque se moveu, a carta criou vaga nova e a antiga ficou duplicando) —
    mas `expire` curto também mata a vaga de carta legítima que pisca, e a
    mão demorava a fechar. Com o teto, `expire` pode ser generoso.

    Recebe detecções já deduplicadas por posição (hand_instances).
    """

    def __init__(self, match_dist: float = 45.0, window: int = 25,
                 min_appear: int = 6, expire: int = 20,
                 max_slots: int | None = None):
        self.match_dist = match_dist
        self.window = window
        self.min_appear = min_appear
        self.expire = expire
        self.max_slots = max_slots
        self._slots: list[dict] = []
        self._displayed: list[str] = []

    def _match(self, cx, cy):
        best, best_d = None, self.match_dist
        for s in self._slots:
            d = ((s["x"] - cx) ** 2 + (s["y"] - cy) ** 2) ** 0.5
            if d < best_d:
                best, best_d = s, d
        return best

    def update(self, detections) -> bool:
        """detections: objetos com .card.code, .confidence e .box (x1,y1,x2,y2).
        Um frame sem detecções (mão fora) NÃO expira nada — congela."""
        if not detections:
            return False

        seen = set()
        for d in detections:
            cx = (d.box[0] + d.box[2]) / 2
            cy = (d.box[1] + d.box[3]) / 2
            slot = self._match(cx, cy)
            if slot is None:
                slot = {"x": cx, "y": cy, "votes": deque(maxlen=self.window),
                        "misses": 0}
                self._slots.append(slot)
            # posição segue a carta suavemente (média móvel)
            slot["x"] = 0.7 * slot["x"] + 0.3 * cx
            slot["y"] = 0.7 * slot["y"] + 0.3 * cy
            slot["votes"].append((d.card.code, d.confidence))
            slot["misses"] = 0
            seen.add(id(slot))

        # vagas não vistas neste frame acumulam ausência e podem expirar
        for s in self._slots:
            if id(s) not in seen:
                s["misses"] += 1
        self._slots = [s for s in self._slots if s["misses"] < self.expire]

        return self._recompute()

    @staticmethod
    def _weight(votes) -> float:
        """Força da vaga: confiança acumulada de tudo que ela já viu."""
        return sum(confidence for _code, confidence in votes)

    @staticmethod
    def _winner(votes) -> str:
        """Rótulo com maior confiança ACUMULADA na vaga.

        Empate desempata pelo código, só para a saída ser determinística.
        """
        totals: Counter = Counter()
        for code, confidence in votes:
            totals[code] += confidence
        return max(totals.items(), key=lambda kv: (kv[1], kv[0]))[0]

    def _recompute(self) -> bool:
        confirmed = [s for s in self._slots if len(s["votes"]) >= self.min_appear]
        if self.max_slots is not None and len(confirmed) > self.max_slots:
            # sobrou vaga: corta pelas MENOS vistas recentemente. `misses`
            # vem primeiro de propósito — depois de o leque se mover, a vaga
            # velha ainda é "forte" (muitos votos) mas está ausente, e quem
            # tem de ganhar é a vaga nova, que é a que corresponde à carta.
            confirmed.sort(key=lambda s: (s["misses"], -self._weight(s["votes"])))
            confirmed = confirmed[:self.max_slots]
        confirmed.sort(key=lambda s: s["x"])
        cards = [self._winner(s["votes"]) for s in confirmed]
        if cards != self._displayed:
            self._displayed = cards
            return True
        return False

    @property
    def cards(self) -> list[str]:
        return list(self._displayed)

    def reset(self):
        self._slots.clear()
        self._displayed = []
