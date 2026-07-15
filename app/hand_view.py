class HandView:
    """Mantém a mão exibida com histerese por carta.

    - Carta entra após `appear_frames` frames consecutivos detectada.
    - Carta sai após `absent_frames` frames consecutivos ausente, mas só
      enquanto OUTRAS cartas continuam visíveis (fantasma expira).
    - Nenhuma detecção no frame = mão fora do quadro: congela tudo.
    """

    def __init__(self, appear_frames: int, absent_frames: int):
        self.appear_frames = appear_frames
        self.absent_frames = absent_frames
        self._seen: dict[str, int] = {}     # candidatos: frames consecutivos vistos
        self._missing: dict[str, int] = {}  # na mão: frames consecutivos ausentes
        self.cards: set[str] = set()

    def update(self, codes: frozenset[str]) -> bool:
        """Processa um frame; retorna True se a mão exibida mudou."""
        if not codes:
            self._seen.clear()
            for code in self._missing:
                self._missing[code] = 0
            return False

        changed = False
        for code in codes:
            if code in self.cards:
                self._missing[code] = 0
            else:
                self._seen[code] = self._seen.get(code, 0) + 1
                if self._seen[code] >= self.appear_frames:
                    self.cards.add(code)
                    self._missing[code] = 0
                    del self._seen[code]
                    changed = True

        for code in list(self._seen):
            if code not in codes:
                del self._seen[code]  # quebrou a sequência: recomeça

        for code in list(self.cards):
            if code not in codes:
                self._missing[code] = self._missing.get(code, 0) + 1
                if self._missing[code] >= self.absent_frames:
                    self.cards.discard(code)
                    self._missing.pop(code, None)
                    changed = True

        return changed

    def reset(self):
        self._seen.clear()
        self._missing.clear()
        self.cards.clear()
