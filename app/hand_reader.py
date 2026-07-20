from collections import Counter, deque


class FanReader:
    """Lê o leque com votação temporal por posição ("vaga").

    Cada carta do leque ocupa uma posição estável na imagem. A cada frame,
    as detecções são casadas a vagas pela proximidade; cada vaga acumula os
    rótulos vistos numa janela recente e exibe o MAIS VOTADO. Isso:
    - estabiliza (o rótulo certo, maioria, vence as leituras erradas);
    - mata fantasmas (detecção esporádica não atinge o mínimo de aparições);
    - preserva gêmeas (posições distintas = vagas distintas);
    - some quando a mão abaixa (vagas expiram por ausência).

    Recebe detecções já deduplicadas por posição (hand_instances).
    """

    def __init__(self, match_dist: float = 45.0, window: int = 25,
                 min_appear: int = 6, expire: int = 20):
        self.match_dist = match_dist
        self.window = window
        self.min_appear = min_appear
        self.expire = expire
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
        """detections: lista de objetos com .card.code e .box (x1,y1,x2,y2).
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
            slot["votes"].append(d.card.code)
            slot["misses"] = 0
            seen.add(id(slot))

        # vagas não vistas neste frame acumulam ausência e podem expirar
        for s in self._slots:
            if id(s) not in seen:
                s["misses"] += 1
        self._slots = [s for s in self._slots if s["misses"] < self.expire]

        return self._recompute()

    def _recompute(self) -> bool:
        confirmed = [s for s in self._slots if len(s["votes"]) >= self.min_appear]
        confirmed.sort(key=lambda s: s["x"])
        cards = [Counter(s["votes"]).most_common(1)[0][0] for s in confirmed]
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
