from collections import Counter


class StableHand:
    """ACOMPANHA a mão do leque, filtrando o tremor do modelo.

    Recebe, a cada frame, a leitura ao vivo (lista de códigos, já votada
    por posição pelo FanReader). Mantém um "score de presença" por carta:
    sobe quando a carta aparece, cai devagar quando some. As cartas com
    score alto formam o conjunto candidato. Quando esse conjunto fica
    ESTÁVEL por `lock_frames` frames e é diferente do que está exibido, a
    exibição é atualizada — automaticamente, sem botão.

    NÃO sabe quantas cartas a mão tem, e isso é requisito: o mesmo leitor vai
    servir a pôquer (2), truco (3), pif-paf e cacheta (9). Qualquer tamanho
    estável é aceito.

    Até 2026-08-19 só eram aceitos os tamanhos `0`, `hand_size` e
    `hand_size + 1`, para não exibir a bagunça da transição — no ato de pôr ou
    tirar uma carta a mão passa na frente e a leitura desce a 6-8 por um
    segundo. Quem faz esse trabalho agora é só a estabilidade: essa bagunça não
    fica parada, então não sobrevive a `lock_frames`. O custo é que uma leitura
    incompleta MAS estável passa a ser exibida — inevitável, já que "incompleta"
    só existe quando se sabe o tamanho certo, e agora não se sabe.

    Versões anteriores travavam a mão UMA vez e seguravam até o botão "Reler
    mão", para o overlay nunca oscilar numa live. Trocado a pedido: o custo
    era ter de clicar a cada carta comprada, e a mão exibida ficava velha.
    A estabilidade agora vem só da histerese (score + `lock_frames`).
    """

    def __init__(self, rise: float = 0.34,
                 decay: float = 0.06, in_thresh: float = 0.5,
                 lock_frames: int = 12):
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

        # Qualquer tamanho serve — o leitor não sabe que jogo é este. A única
        # exigência é ESTABILIDADE: a bagunça da transição (a mão passando na
        # frente, cartas ocultas, frames borrados) muda de tamanho a cada
        # frame e não sobrevive a `lock_frames`.
        if (self._stable >= self.lock_frames
                and cand_key != tuple(sorted(self._locked))):
            self._locked = list(candidate)
            return True
        return False

    @property
    def cards(self) -> list[str]:
        """A mão travada, na ordem FÍSICA mais recente que se conhece.

        O CONJUNTO é o travado — é ele que dá estabilidade e gera evento. A
        ORDEM, não: ela acompanha a leitura viva sempre que essa leitura mostra
        exatamente as mesmas cartas.

        Antes a ordem congelava no instante da trava, e havia um jeito garantido
        de sair errada: a carta que estivesse ausente NAQUELE frame não tinha
        posição conhecida e ia para o FIM da lista (ver `_candidate`) — onde
        ficava até a próxima troca de mão, mesmo depois de reaparecer no lugar
        certo. É o que o jogador vê ao encaixar uma carta no meio do leque:
        medido numa partida de 5 min, 16,9% dos frames com a mão certa tinham a
        ordem errada, sempre a carta nova jogada para o fim.

        A ordem só é atualizada quando a leitura viva bate em CONJUNTO com a
        travada. Enquanto o leitor estiver mostrando outra coisa (carta oculta,
        transição), a última ordem boa é preservada — senão o overlay ficaria
        remexendo as cartas a cada frame borrado, que é o problema oposto.
        """
        if self._locked and Counter(self._last_live) == Counter(self._locked):
            return list(self._last_live)
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
