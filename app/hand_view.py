from collections import Counter


class HandView:
    """Mantém a mão exibida com histerese por carta, suportando gêmeas
    (cacheta usa 2 baralhos — pode haver duas cartas idênticas na mão).

    - Contagem de um rótulo SOBE após `appear_frames` frames consecutivos
      observando mais instâncias do que as exibidas.
    - Contagem DESCE após `absent_frames` frames consecutivos observando
      menos — mas só enquanto OUTRAS cartas continuam visíveis.
    - Nenhuma detecção no frame = mão fora do quadro: congela tudo.
    """

    def __init__(self, appear_frames: int, absent_frames: int):
        self.appear_frames = appear_frames
        self.absent_frames = absent_frames
        self.counts: Counter = Counter()  # exibido: código -> quantidade
        self._grow: dict[str, int] = {}
        self._shrink: dict[str, int] = {}

    def update(self, observed: Counter) -> bool:
        """Processa um frame; retorna True se a mão exibida mudou."""
        if not observed:
            self._grow.clear()
            self._shrink.clear()
            return False

        changed = False
        for code in set(observed) | set(self.counts):
            obs = observed.get(code, 0)
            cur = self.counts.get(code, 0)
            if obs > cur:
                self._shrink.pop(code, None)
                self._grow[code] = self._grow.get(code, 0) + 1
                if self._grow[code] >= self.appear_frames:
                    self.counts[code] = obs
                    self._grow.pop(code)
                    changed = True
            elif obs < cur:
                self._grow.pop(code, None)
                self._shrink[code] = self._shrink.get(code, 0) + 1
                if self._shrink[code] >= self.absent_frames:
                    if obs:
                        self.counts[code] = obs
                    else:
                        del self.counts[code]
                    self._shrink.pop(code)
                    changed = True
            else:
                self._grow.pop(code, None)
                self._shrink.pop(code, None)
        return changed

    @property
    def cards(self) -> list[str]:
        return [code for code, n in self.counts.items() for _ in range(n)]

    def reset(self):
        self._grow.clear()
        self._shrink.clear()
        self.counts.clear()
