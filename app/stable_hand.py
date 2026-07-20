from collections import Counter


class StableHand:
    """Trava a mão do leque para o overlay ficar ESTÁVEL numa live.

    Recebe, a cada frame, a leitura ao vivo (lista de códigos, já votada
    por posição pelo FanReader). Mantém um "score de presença" por carta:
    sobe quando a carta aparece, cai devagar quando some. As cartas com
    score alto formam o conjunto candidato. Quando o candidato fica com
    `hand_size` cartas ESTÁVEL por `lock_frames` frames, ele é TRAVADO e
    exibido — e não muda mais com o tremor do modelo. Só re-trava quando um
    conjunto diferente de `hand_size` fica estável (o jogador descartou e
    comprou) ou quando `force_relock()`/`reset()` é chamado.
    """

    def __init__(self, hand_size: int = 9, rise: float = 0.34,
                 decay: float = 0.06, in_thresh: float = 0.5,
                 lock_frames: int = 12):
        self.hand_size = hand_size
        self.rise = rise          # quanto o score sobe por aparição
        self.decay = decay        # quanto cai por frame ausente
        self.in_thresh = in_thresh
        self.lock_frames = lock_frames
        self._score: dict[str, float] = {}
        self._last_candidate: tuple = ()
        self._stable = 0
        self._locked: list[str] = []

    def _candidate(self) -> list[str]:
        # multiconjunto: repete a carta conforme quantas instâncias têm score alto
        counts = Counter()
        for key, sc in self._score.items():
            if sc >= self.in_thresh:
                code, _idx = key
                counts[code] += 1
        out = []
        for code in sorted(counts):
            out.extend([code] * counts[code])
        return out

    def update(self, live_cards) -> bool:
        # score por instância: 7H,7H viram (7H,0) e (7H,1)
        seen = Counter()
        present = set()
        for code in live_cards:
            key = (code, seen[code])
            seen[code] += 1
            present.add(key)
            self._score[key] = min(1.0, self._score.get(key, 0.0) + self.rise)
        for key in list(self._score):
            if key not in present:
                self._score[key] -= self.decay
                if self._score[key] <= 0:
                    del self._score[key]

        candidate = self._candidate()
        cand_key = tuple(candidate)
        if cand_key == self._last_candidate:
            self._stable += 1
        else:
            self._last_candidate = cand_key
            self._stable = 1

        # trava UMA vez quando um conjunto de hand_size fica estável e
        # SEGURA — só re-lê após force_relock() (botão "Reler mão") ou
        # reset(). Assim o movimento/erro do modelo não troca a mão travada.
        if (not self._locked
                and len(candidate) == self.hand_size
                and self._stable >= self.lock_frames):
            self._locked = list(candidate)
            return True
        return False

    @property
    def cards(self) -> list[str]:
        return list(self._locked)

    @property
    def live_count(self) -> int:
        return len(self._candidate())

    def force_relock(self):
        """Esquece tudo e relê do zero: o próximo 9 estável trava."""
        self._score.clear()
        self._last_candidate = ()
        self._stable = 0
        self._locked = []

    def reset(self):
        self._score.clear()
        self._last_candidate = ()
        self._stable = 0
        self._locked = []
