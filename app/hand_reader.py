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

    A "posição estável" só existe depois de descontar o movimento da mão: o
    leque inteiro translada junto a cada tremor. `_estimate_shift` mede essa
    translação comum e desloca as vagas antes de casar — sem isso, o jitter
    medido (66px p95) supera o raio de casamento e a mesma carta cria vaga
    nova a cada frame.

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
                 max_slots: int | None = None,
                 shift_tol: float = 20.0, max_shift: float = 200.0,
                 win_margin: float = 1.6):
        self.match_dist = match_dist
        self.window = window
        self.min_appear = min_appear
        self.expire = expire
        self.max_slots = max_slots
        # compensação de movimento: `shift_tol` é o quanto dois deslocamentos
        # podem diferir e ainda votarem juntos (folga para o ruído por carta);
        # precisa ficar bem abaixo do espaçamento entre cartas, senão o
        # deslocamento "carta i -> vaga i+1" entra no mesmo voto.
        self.shift_tol = shift_tol
        self.max_shift = max_shift      # movimento maior que isso é implausível
        # Histerese do rótulo: para TROCAR a carta de uma vaga já estabelecida,
        # a concorrente precisa ganhar por esta margem. Sem isso, alguns frames
        # borrados (câmera tremendo) viram o rótulo, a mão exibida muda sozinha
        # para uma carta que nem está no leque, e a mudança ainda gera compra e
        # descarte fantasmas. Estabelecer um rótulo continua fácil; derrubar um
        # já estabelecido é que passa a ser difícil.
        self.win_margin = win_margin
        self._slots: list[dict] = []
        self._displayed: list[str] = []
        self._empty = 0                 # frames seguidos sem NENHUMA detecção
        self._occluded = 0              # frames seguidos de leque fechado

    def _match(self, cx, cy):
        """Vaga mais próxima dentro do raio, e a distância até ela."""
        best, best_d = None, self.match_dist
        for s in self._slots:
            d = ((s["x"] - cx) ** 2 + (s["y"] - cy) ** 2) ** 0.5
            if d < best_d:
                best, best_d = s, d
        return best, best_d

    def _estimate_shift(self, centers) -> tuple[float, float]:
        """Translação COMUM do leque desde o frame anterior.

        A mão move o leque inteiro junto: as cartas não se deslocam umas em
        relação às outras. Medido no setup real, o tremor chega a 66px (p95)
        enquanto as cartas vizinhas ficam a 69px (p05) — sem compensar, a
        mesma carta sai da própria vaga e cria vaga nova a cada tremor.

        Estimativa por VOTAÇÃO, não por média dos pares mais próximos: com
        deslocamento maior que meia distância entre cartas, o vizinho mais
        próximo já é a carta errada e a média sairia viciada. Aqui cada par
        (detecção, vaga) propõe um deslocamento; o verdadeiro é proposto uma
        vez por carta casada, os espúrios se espalham. Vence quem tem mais
        votos dentro de `shift_tol`, e só se houver suporte de metade das
        vagas — senão é ruído e não movimento, e não se mexe em nada.
        """
        if not self._slots or not centers:
            return 0.0, 0.0
        offsets = [(cx - s["x"], cy - s["y"])
                   for cx, cy in centers for s in self._slots]
        offsets = [(ox, oy) for ox, oy in offsets
                   if abs(ox) <= self.max_shift and abs(oy) <= self.max_shift]
        if not offsets:
            return 0.0, 0.0

        best, best_n = (0.0, 0.0), 0
        for ox, oy in offsets:
            n = sum(1 for px, py in offsets
                    if abs(px - ox) <= self.shift_tol
                    and abs(py - oy) <= self.shift_tol)
            if n > best_n:
                best, best_n = (ox, oy), n
        if best_n < max(2, len(self._slots) // 2):
            return 0.0, 0.0

        inliers = [(ox, oy) for ox, oy in offsets
                   if abs(ox - best[0]) <= self.shift_tol
                   and abs(oy - best[1]) <= self.shift_tol]
        return (sum(o[0] for o in inliers) / len(inliers),
                sum(o[1] for o in inliers) / len(inliers))

    def update(self, detections) -> bool:
        """detections: objetos com .card.code, .confidence e .box (x1,y1,x2,y2).

        Frame sem NENHUMA detecção é ambíguo: pode ser a mão saindo do quadro
        ou o modelo falhando por um instante. Segura por `expire` frames (a
        mesma folga usada para a vaga individual) e, se continuar vazio, a mão
        some — o jogador que abaixou as cartas espera ver zero, não a mão
        anterior congelada para sempre.
        """
        if not detections:
            self._empty += 1
            if self._empty < self.expire or not (self._slots or self._displayed):
                return False
            self._slots.clear()
            mudou = self._displayed != []
            self._displayed = []
            return mudou
        self._empty = 0

        # QUEDA BRUSCA = oclusão, não jogada. Na cacheta a mão muda de UMA
        # carta por vez, então ver 1 carta onde havia 9 é o leque fechando (as
        # outras ficam atrás da primeira) ou a mão passando na frente. Congela:
        # não expira vaga e não mexe na exibição.
        #
        # Sem isso, fechar o leque expirava as 8 vagas ocultas, e ao reabrir
        # elas nasciam sem histórico de votos — o leitor "esquecia" o que já
        # tinha acertado e podia estabelecer rótulo errado do zero. Congelando,
        # os votos acumulados sobrevivem e a leitura certa volta na hora.
        if self._displayed and len(detections) < len(self._displayed) - 1:
            self._occluded += 1
            return False

        # Ao REABRIR, a duração da oclusão diz se as vagas ainda valem.
        #
        # Oclusão CURTA (a mão passando na frente) não mexe no leque: as cartas
        # voltam onde estavam e os votos acumulados são o que faz a leitura
        # certa voltar no primeiro frame. É para isso que o congelamento existe.
        #
        # Oclusão LONGA é o leque fechado — e na cacheta se fecha o leque
        # justamente para encaixar a carta comprada. Ao reabrir, o leque foi
        # remontado e nada está onde estava. Casar o leque novo nas vagas
        # velhas faz cada vaga teimar com o rótulo antigo: são 30 votos
        # acumulados contra os poucos da carta que chegou, e ainda por cima a
        # margem de histerese. A mão sai remontada nas posições erradas,
        # estável o bastante para ser aceita — e a "carta nova" que o tracker
        # deduz do diff é qualquer uma, menos a que o jogador comprou.
        #
        # `expire` separa os dois casos porque já é a medida de "ausência
        # tolerável" do leitor: passou disso, trate como leque novo e releia.
        # Custo: ~1 s a mais para a mão aparecer depois de reabrir.
        if self._occluded:
            if self._occluded >= self.expire:
                self._slots.clear()
            self._occluded = 0

        centers = [((d.box[0] + d.box[2]) / 2, (d.box[1] + d.box[3]) / 2)
                   for d in detections]
        shift_x, shift_y = self._estimate_shift(centers)
        if shift_x or shift_y:
            for s in self._slots:
                s["x"] += shift_x
                s["y"] += shift_y

        # UMA detecção por vaga. Duas cartas não ocupam a mesma posição física
        # no mesmo frame, mas o casamento por proximidade permitia isso: num
        # leque apertado as duas caíam dentro do raio da MESMA vaga e as duas
        # votavam nela. A vaga virava um empate técnico entre dois rótulos
        # (medido ao vivo: 9S=13.86 contra 7C=13.34) e a perdedora sumia da
        # mão — o leitor entregava 9 cartas onde havia 10, e o tracker via
        # "entrou uma e saiu outra", que ele ignora de propósito. É a origem
        # do sintoma antigo "carta some e a vizinha duplica".
        #
        # Quem fica com a vaga é a detecção MAIS PRÓXIMA dela, não a primeira
        # da lista: senão o resultado dependia da ordem em que o modelo
        # devolveu as caixas, e a carta legítima podia perder a própria vaga
        # (com os votos acumulados dela) para a intrusa. O que acontece com
        # quem perde depende do RÓTULO — ver o comentário no laço abaixo.
        candidatos = []
        for d in detections:
            cx = (d.box[0] + d.box[2]) / 2
            cy = (d.box[1] + d.box[3]) / 2
            slot, dist = self._match(cx, cy)
            candidatos.append((d, cx, cy, slot, dist))
        mais_perto: dict[int, tuple[float, str]] = {}
        for d, _cx, _cy, slot, dist in candidatos:
            if slot is not None:
                key = id(slot)
                if key not in mais_perto or dist < mais_perto[key][0]:
                    mais_perto[key] = (dist, d.card.code)

        seen = set()
        tomadas: set[int] = set()
        for d, cx, cy, slot, dist in candidatos:
            if slot is not None and (id(slot) in tomadas
                                     or dist > mais_perto[id(slot)][0]):
                # Perdeu a disputa. O RÓTULO diz o que ela é de verdade:
                #
                # - rótulo IGUAL ao do vencedor = o mesmo canto lido duas
                #   vezes. Medido ao vivo: o A♠ saiu numa vaga a 42 px da
                #   própria, com confiança 0.55 contra 0.94 da leitura boa —
                #   perto o bastante para disputar a vaga, longe o bastante
                #   para escapar da fusão do `hand_instances` (~15 px). Abrir
                #   vaga para ela duplicava a carta na mão e gerava compra e
                #   descarte fantasmas. Descarta.
                # - rótulo DIFERENTE = é outra carta, encostada na vizinha.
                #   Esse é o caso que a regra de uma-por-vaga existe para
                #   resolver, e aí a vaga nova é legítima.
                if d.card.code == mais_perto[id(slot)][1]:
                    continue
                slot = None       # outra detecção está mais perto desta vaga
            if slot is None:
                slot = {"x": cx, "y": cy, "votes": deque(maxlen=self.window),
                        "misses": 0, "label": None}
                self._slots.append(slot)
            tomadas.add(id(slot))
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

        self._funde_vagas_gemeas()
        return self._recompute()

    def _rotulo_bruto(self, s) -> str | None:
        """O que a vaga é hoje: o rótulo exibido, ou o mais votado se não há."""
        if s["label"]:
            return s["label"]
        if not s["votes"]:
            return None
        totals: Counter = Counter()
        for code, confidence in s["votes"]:
            totals[code] += confidence
        return max(totals.items(), key=lambda kv: (kv[1], kv[0]))[0]

    def _funde_vagas_gemeas(self):
        """Duas vagas vizinhas com o MESMO rótulo são a mesma carta.

        É o outro lado da regra de uma-detecção-por-vaga, e a brecha que ela
        deixava: aquela regra descarta a leitura repetida quando as duas
        DISPUTAM a mesma vaga. Se as duas vagas já existirem — cada detecção
        casando com a sua — não há disputa nenhuma e a duplicata se perpetua.
        Medido ao vivo: o A♥ ficou em duas vagas a 48 px uma da outra
        (pesos 19.77 e 4.66), a mão exibida saiu com dois ases de copas e o
        tracker emitiu compra fantasma do próprio ás.

        O raio é o mesmo `match_dist` do casamento, e isso não ameaça as
        gêmeas legítimas dos dois baralhos: cantos vizinhos num leque real
        ficam a 44-111 px (p05 = 69), bem acima dele. Abaixo de `match_dist`
        duas detecções já cairiam na mesma vaga de qualquer jeito.

        Fica a vaga mais FORTE (maior confiança acumulada). Os votos da fraca
        são descartados em vez de somados: eles são leitura do mesmo canto,
        então somar seria contar a mesma evidência duas vezes.
        """
        if len(self._slots) < 2:
            return
        ordenadas = sorted(self._slots,
                           key=lambda s: -self._weight(s["votes"]))
        mantidas: list[dict] = []
        for s in ordenadas:
            rotulo = self._rotulo_bruto(s)
            gemea = False
            for k in mantidas:
                if rotulo is None or self._rotulo_bruto(k) != rotulo:
                    continue
                d = ((k["x"] - s["x"]) ** 2 + (k["y"] - s["y"]) ** 2) ** 0.5
                if d < self.match_dist:
                    gemea = True
                    break
            if not gemea:
                mantidas.append(s)
        self._slots = mantidas

    @staticmethod
    def _weight(votes) -> float:
        """Força da vaga: confiança acumulada de tudo que ela já viu."""
        return sum(confidence for _code, confidence in votes)

    def _winner(self, votes, atual: str | None = None) -> str:
        """Rótulo com maior confiança ACUMULADA na vaga.

        Se a vaga já tem um rótulo (`atual`), ele só cai quando a concorrente
        o supera por `win_margin` — histerese que impede o rótulo de piscar a
        cada frame borrado. Empate desempata pelo código, para a saída ser
        determinística.
        """
        totals: Counter = Counter()
        for code, confidence in votes:
            totals[code] += confidence
        campeao = max(totals.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if atual is None or campeao == atual:
            return campeao
        if totals[campeao] < totals[atual] * self.win_margin:
            return atual          # não ganhou por margem: mantém o que estava
        return campeao

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
        cards = []
        for s in confirmed:
            s["label"] = self._winner(s["votes"], s.get("label"))
            cards.append(s["label"])
        if cards != self._displayed:
            self._displayed = cards
            return True
        return False

    @property
    def cards(self) -> list[str]:
        return list(self._displayed)

    def slots_debug(self) -> list[dict]:
        """Estado das vagas para diagnóstico (usado no log da trava).

        Distingue as duas causas que produzem a MESMA mão errada: rótulo
        repetido em vagas de posições diferentes (o modelo leu duas cartas
        como a mesma) x vaga duplicada no mesmo lugar (o casamento por
        posição se perdeu). Sem isso, só o resultado final é visível e as
        duas hipóteses ficam indistinguíveis.
        """
        out = []
        for s in sorted(self._slots, key=lambda s: s["x"]):
            totals: Counter = Counter()
            for code, confidence in s["votes"]:
                totals[code] += confidence
            out.append({
                "x": round(s["x"]),
                "y": round(s["y"]),
                "n": len(s["votes"]),
                "misses": s["misses"],
                "top": [(code, round(peso, 2))
                        for code, peso in totals.most_common(3)],
            })
        return out

    def reset(self):
        self._slots.clear()
        self._displayed = []
        self._empty = 0
        self._occluded = 0
