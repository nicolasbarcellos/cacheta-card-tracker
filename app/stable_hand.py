from collections import Counter


class StableHand:
    """ACOMPANHA a mão do leque, filtrando o tremor do modelo.

    Recebe, a cada frame, a leitura ao vivo (lista de códigos, já votada
    por posição pelo FanReader). Mantém um "score de presença" por carta:
    sobe quando a carta aparece, cai devagar quando some. As cartas com
    score alto formam o conjunto candidato. Quando esse conjunto fica
    ESTÁVEL por `lock_frames` frames e é diferente do que está exibido, a
    exibição é atualizada — automaticamente, sem botão.

    O `hand_size` NÃO é exigido: a mão tem 9 cartas na maior parte do tempo
    mas passa por 10 no instante da compra, e o jogador espera ver as 10.
    Ele serve só para dimensionar o teto de vagas do FanReader lá fora.

    Versões anteriores travavam a mão UMA vez e seguravam até o botão "Reler
    mão", para o overlay nunca oscilar numa live. Trocado a pedido: o custo
    era ter de clicar a cada carta comprada, e a mão exibida ficava velha.
    A estabilidade agora vem só da histerese (score + `lock_frames`).
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
        self._last_live: list[str] = []
        self._stable = 0
        self._locked: list[str] = []

    def _candidate(self) -> list[str]:
        """Multiconjunto das cartas com score alto, NA ORDEM da leitura viva.

        A ordem é informação, não detalhe: o FanReader entrega as vagas da
        esquerda para a direita, que é a ordem física do leque na mão do
        jogador. Ordenar por código aqui (como era antes) jogava isso fora e
        o overlay mostrava a mão embaralhada.
        """
        counts: Counter = Counter()
        for key, sc in self._score.items():
            if sc >= self.in_thresh:
                code, _idx = key
                counts[code] += 1
        out: list[str] = []
        usados: Counter = Counter()
        for code in self._last_live:        # ordem física, esquerda -> direita
            if usados[code] < counts[code]:
                out.append(code)
                usados[code] += 1
        # carta com score alto que sumiu neste frame ainda conta; sem posição
        # conhecida, vai para o fim em ordem determinística
        for code in sorted(counts):
            while usados[code] < counts[code]:
                out.append(code)
                usados[code] += 1
        return out

    def update(self, live_cards) -> bool:
        # score por instância: 7H,7H viram (7H,0) e (7H,1)
        self._last_live = list(live_cards)
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
        # a ESTABILIDADE olha o conjunto, não a ordem: duas cartas trocando de
        # lugar por um tremor não é mão nova e não pode reiniciar a contagem.
        # A ordem, essa, é preservada em `candidate` para a exibição.
        cand_key = tuple(sorted(candidate))
        if cand_key == self._last_candidate:
            self._stable += 1
        else:
            self._last_candidate = cand_key
            self._stable = 1

        # ACOMPANHA, mas só aceita mão PLAUSÍVEL: vazia (jogador abaixou as
        # cartas), `hand_size` (mão normal) ou `hand_size + 1` (instante da
        # compra). Qualquer outro tamanho é bagunça de transição — no ato
        # físico de pôr ou tirar uma carta a mão passa na frente, cartas ficam
        # ocultas e os frames borram, e a leitura desce a 6, 7, 8 por um
        # segundo. Sem este filtro a tela mostrava essa bagunça, que é o que
        # dava a sensação de "ele fica trocando as cartas sozinho".
        #
        # O custo: se a leitura de fato estabilizar num tamanho inesperado, a
        # tela segura a mão anterior em vez de mostrar uma mão incompleta.
        # É o comportamento pedido — travado, e mudando só para mão inteira.
        tamanhos_plausiveis = (0, self.hand_size, self.hand_size + 1)
        if (self._stable >= self.lock_frames
                and len(candidate) in tamanhos_plausiveis
                and cand_key != tuple(sorted(self._locked))):
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
        self._last_live = []
        self._stable = 0
        self._locked = []

    def reset(self):
        self._score.clear()
        self._last_candidate = ()
        self._last_live = []
        self._stable = 0
        self._locked = []
