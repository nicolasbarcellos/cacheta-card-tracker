from collections import Counter, deque

# Fração da mão exibida que ainda pode estar visível para o leitor tratar o
# frame como OCLUSÃO (leque fechado, mão na frente) em vez de leitura nova.
# Ver o bloco de comentário em `update` — é o que impede o congelamento de
# virar estado absorvente. 0,6 fica entre a oclusão real (11-33% visível na
# medição) e a mão exibida inchada (75%), com folga dos dois lados.
FRACAO_OCLUSAO = 0.6


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
                 win_margin: float = 1.6,
                 frame_w: int = 0, frame_h: int = 0, borda: float = 0.0,
                 peso_min: float = 0.0, vao_grupo: float = 0.0):
        self.match_dist = match_dist
        # Zona morta nas bordas do quadro. Uma carta que desce abaixo do
        # enquadramento tem o índice CORTADO, e o modelo palpita em cima de
        # meio glifo. Medido na partida de 2026-08-11: o 4♦ fantasma, que
        # gerou quatro eventos falsos, saía de caixas com `y2` exatamente
        # 1080 (a borda) e confiança mediana 0,43, contra 0,93 das cartas de
        # verdade. Só 2% das detecções da partida ficam coladas na borda, mas
        # 34% das do fantasma ficavam.
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.borda = borda
        # Piso de peso RELATIVO à mediana das vagas — ver `_recompute`.
        self.peso_min = peso_min
        # Vão que separa a carta segurada à parte do leque — ver `_so_o_leque`.
        self.vao_grupo = vao_grupo
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
        # O que o leitor considerou LEQUE no último frame (depois de
        # `_so_o_leque`). Não é usado pela leitura — existe para a MEDIÇÃO.
        # A contradição pergunta "esta carta está visível e não está na tela?",
        # e a carta segurada à parte está visível de propósito fora da tela:
        # cobrá-la é medir o comportamento pedido como se fosse defeito. Medido
        # na partida de 19/08, a diferença entre cobrar e não cobrar era de
        # 7,5% para 9,2%. Publicar aqui evita a alternativa, que seria a
        # medição reimplementar o agrupamento e divergir do leitor sem aviso.
        self.ultimo_leque: list = []
        # CONGELADO: neste frame o leitor decidiu não mexer na mão — leque
        # fechado / mão na frente (oclusão) ou quadro sem detecção nenhuma.
        # Existe pela mesma razão que `ultimo_leque`: a métrica precisa saber o
        # que o leitor DECIDIU, e uma cópia da regra dentro dela divergiria em
        # silêncio. Medido em 2026-08-24: 16-51% dos frames de excesso estão
        # neste estado, em que segurar a mão é o comportamento pedido e não
        # defeito — ver `app/leitura.py`.
        self.congelado = False
        # Quantas vezes cada código apareceu no quadro em cada um dos últimos
        # `window` frames. É a base do teto por código — ver `_recompute`.
        self._vistos: deque = deque(maxlen=window)

    def _cortada(self, box) -> bool:
        """A caixa encosta na borda do quadro, então o índice está amputado.

        Vale só para NASCER vaga. Votar numa vaga existente continua
        permitido: uma carta de verdade que desliza para a borda deve manter
        a vaga viva — suprimir o voto dela a mataria mais rápido, que é o
        problema oposto (e foi o do 3♦ na mesma partida).
        """
        if not (self.borda and self.frame_w and self.frame_h):
            return False
        x1, y1, x2, y2 = box
        return (x1 <= self.borda or y1 <= self.borda
                or x2 >= self.frame_w - self.borda
                or y2 >= self.frame_h - self.borda)

    def _so_o_leque(self, detections):
        """Só as detecções do LEQUE — a carta segurada à parte não é da mão.

        O jogador pega a carta com a outra mão e fica com ela fora do leque
        enquanto decide onde encaixar. Sem esta regra o leitor já a mostrava
        como carta da mão, antes de ela chegar lá — foi o primeiro defeito que
        o usuário apontou ao testar o leitor rápido.

        O leque é uma CORRENTE: cada carta encosta na vizinha. Basta então
        ligar as detecções vizinhas em x que estejam perto o bastante e ficar
        com o maior grupo. A carta separada não se liga a ninguém e cai.

        A distância é medida em LARGURAS DE CAIXA, para não depender de quão
        perto da câmera está o leque. Medido nas duas partidas gravadas
        (142 mil vãos): dentro do leque o vão fica em 0,63-0,70 na mediana e
        1,3-1,9 no p99; acima de 2,5 há só 0,1% dos vãos, que é a cauda da
        carta fora do leque.

        Um grupo separado NÃO é descartado se ele casa com vaga já estabelecida:
        o leque também se parte quando as cartas do meio deixam de ser
        detectadas por um instante, e aí os dois pedaços são da mão — eles têm
        vaga, história de votos, posição conhecida. A carta que acabou de ser
        pega não tem nada disso. Sem essa ressalva a regra custava caro: medido
        na partida de 19/08, a contradição subia de 7,5% para 9,2%.

        Fica então: todo grupo que encosta em vaga existente, mais o MAIOR
        grupo (que é o leque no começo, quando ainda não há vaga nenhuma).
        """
        if not self.vao_grupo or len(detections) < 2:
            return detections
        larguras = sorted(d.box[2] - d.box[0] for d in detections)
        w = larguras[len(larguras) // 2]
        if w <= 0:
            return detections
        limite = self.vao_grupo * w
        ordenadas = sorted(detections,
                           key=lambda d: (d.box[0] + d.box[2]) / 2)
        grupos, atual = [], [ordenadas[0]]
        for ant, d in zip(ordenadas, ordenadas[1:]):
            ax = (ant.box[0] + ant.box[2]) / 2
            ay = (ant.box[1] + ant.box[3]) / 2
            dx = (d.box[0] + d.box[2]) / 2
            dy = (d.box[1] + d.box[3]) / 2
            if ((dx - ax) ** 2 + (dy - ay) ** 2) ** 0.5 <= limite:
                atual.append(d)
            else:
                grupos.append(atual)
                atual = [d]
        grupos.append(atual)
        if len(grupos) == 1:
            return detections

        maior = max(grupos, key=lambda g: (len(g),
                                           sum(d.confidence for d in g)))
        mantidos = []
        for g in grupos:
            if g is maior or any(
                    self._match((d.box[0] + d.box[2]) / 2,
                                (d.box[1] + d.box[3]) / 2)[0] is not None
                    for d in g):
                mantidos += g
        return mantidos

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
        self.congelado = False
        if not detections:
            self.ultimo_leque = []
            self.congelado = True
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
        # ... mas a queda tem de ser GRANDE, e não só de duas cartas. Sem essa
        # segunda condição a regra tem um estado ABSORVENTE, medido em
        # 2026-08-20: se a mão exibida cresce para 12 (vaga velha que ainda não
        # expirou, somada à nova) e o quadro mostra as 9 de verdade, então
        # 9 < 12-1 em TODO frame e o leitor congela PARA SEMPRE. O código que
        # reabre (`_occluded >= expire`, logo abaixo) só roda num frame NÃO
        # congelado, que nunca chega. Na partida de 19/08 16:22 isso deu uma
        # trava única de 1.936 frames (~78 s) exibindo 12 cartas, com a
        # contradição da partida em 50%; ao vivo o mesmo estado aparece menor
        # (175 frames seguidos), mas aparece.
        #
        # `FRACAO_OCLUSAO` separa as duas situações pelo que elas são de fato:
        #
        #   leque fechado    1 carta de 9 visíveis = 11%  -> é oclusão, congela
        #   mão na frente    3 de 9 = 33%                 -> é oclusão, congela
        #   mão exibida INCHADA  9 de 12 = 75%            -> não é oclusão: o
        #                    quadro está mostrando um leque inteiro, e quem
        #                    está errada é a tela. Deixa passar e ela se corrige
        #
        # A regra antiga ("queda de duas ou mais cartas") vinha de a cacheta
        # trocar UMA carta por vez, premissa que caiu com a virada de escopo de
        # 19/08 — a fração não sabe que jogo é este. O que ela relaxa é o caso
        # de duas cartas sumirem de uma vez num leque pequeno; aí quem protege
        # a tela continua sendo o `lock_frames` do StableHand, que exige a
        # leitura nova parada por ~0,7 s.
        if (self._displayed and len(detections) < len(self._displayed) - 1
                and len(detections) < FRACAO_OCLUSAO * len(self._displayed)):
            # o leque não foi agrupado neste frame (o leitor congelou antes
            # disso), mas o pouco que se vê É carta da mão: para a medição,
            # conta como leque — senão a oclusão viraria um buraco na conta
            self.ultimo_leque = list(detections)
            self.congelado = True
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

        # A carta que o jogador segura FORA do leque ainda não é da mão — some
        # daqui e não cria vaga nem vota. Isto vem DEPOIS da checagem de
        # oclusão de propósito: aplicado antes, um leque momentaneamente
        # partido (cartas do meio não detectadas) virava "sumiram 3 cartas",
        # disparava o congelamento e a tela travava. Medido: a contradição ia
        # de 7,5% para 76% e a mão exibida mudava 4 vezes numa partida inteira.
        detections = self._so_o_leque(detections)
        self.ultimo_leque = list(detections)
        self._vistos.append(Counter(d.card.code for d in detections))

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
                # NA BORDA NÃO NASCE CARTA. Não casou com vaga nenhuma e o
                # índice está cortado pelo quadro: é palpite sobre meio glifo,
                # não uma carta a mais na mão. Deixar nascer dava vaga
                # espúria, e vaga espúria na mão de 9 vira COMPRA — o teto de
                # `hand_size + 1` não barra, porque a décima vaga é
                # justamente a que o teto existe para permitir.
                if self._cortada(d.box):
                    continue
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

    def _corta(self, slots: list[dict], teto: int) -> list[dict]:
        """Deixa no máximo `teto` vagas, cortando as MENOS vistas.

        `misses` vem antes do peso de propósito: depois de o leque se mover, a
        vaga velha ainda é "forte" (muitos votos acumulados) mas está ausente,
        e quem tem de ganhar é a vaga nova, que é a que corresponde à carta.
        """
        if len(slots) <= teto:
            return slots
        ordenadas = sorted(slots,
                           key=lambda s: (s["misses"], -self._weight(s["votes"])))
        return ordenadas[:teto]

    def _recompute(self) -> bool:
        confirmed = [s for s in self._slots if len(s["votes"]) >= self.min_appear]
        # PISO DE PESO: vaga muito mais fraca que as vizinhas não é carta.
        #
        # A vaga sobrevive aos frames em que a carta não aparece — é o que faz
        # o leitor aguentar oclusão. O efeito colateral é que a mão exibida
        # vira uma UNIÃO ao longo do tempo, e duas leituras que se excluem
        # podem coexistir nela. Medido na partida de 12/08: o A♥ foi lido como
        # A♦ por meio segundo e nasceu uma vaga a 61 px da do A♥ — perto demais
        # para ser outra carta, longe demais para o casamento fundir. A mão
        # saiu com A♥ MAIS dois A♦: dez cartas que nunca estiveram juntas em
        # frame nenhum, e daí uma compra e um descarte que não aconteceram.
        #
        # A intrusa se distingue por DUAS marcas juntas, e é preciso as duas:
        #
        # - ela DUPLICA uma carta que já está na mão (é um erro de classe, não
        #   uma carta nova);
        # - e é muito mais fraca que as outras: 11,25 de confiança acumulada
        #   contra ~50 das vizinhas.
        #
        # Exigir só o peso não serve, e foi medido: a carta recém-comprada
        # também nasce fraca, e o piso sozinho derrubava compra de verdade —
        # na partida de 11/08, duas compras passaram a sair com a carta errada.
        # Gêmeas de verdade existem (o jogo usa dois baralhos), mas chegam pela
        # compra e engordam como qualquer carta legítima; a duplicada por erro
        # de leitura fica fraca porque disputa confiança com a leitura certa.
        if self.peso_min and len(confirmed) >= 3:
            pesos = {id(s): self._weight(s["votes"]) for s in confirmed}
            ordem = sorted(pesos.values())
            mediana = ordem[len(ordem) // 2]
            rotulos = Counter(self._winner(s["votes"], s.get("label"))
                              for s in confirmed)
            confirmed = [
                s for s in confirmed
                if not (rotulos[self._winner(s["votes"], s.get("label"))] > 1
                        and mediana > 0
                        and pesos[id(s)] < self.peso_min * mediana)]
        # TETO POR CÓDIGO: a mesma carta não pode estar na mão mais vezes do que
        # o quadro chegou a mostrar DE UMA VEZ na janela recente.
        #
        # Medido na partida de 20/08, a primeira gravada sem o teto de vagas
        # (`max_slots`, removido em 19/08 junto com "não assumir o jogo"):
        # **44,5% dos frames exibiam 17 cartas**, com a mesma carta repetida
        # TRÊS vezes (`5D 5D`, `KC KC KC`, `7D 7D 7D`). Todas as gravações
        # anteriores param em 10, que era exatamente o teto antigo. As guardas
        # que ficaram no lugar dele não seguram vaga órfã: `fan_peso_min` só
        # mata duplicata FRACA, e a órfã de um leque que se moveu é forte —
        # carrega os votos acumulados de quando a carta estava ali.
        #
        # Este teto não sabe que jogo é este, que era o requisito da virada de
        # escopo: ele não diz quantas cartas a mão tem, diz que uma carta não
        # está em três lugares se nunca foi vista em três lugares no mesmo
        # frame. Com dois baralhos, gêmeas legítimas aparecem juntas em algum
        # frame e sobrevivem; a órfã, não.
        #
        # O máximo é tirado da JANELA e não do frame atual, senão a carta
        # momentaneamente encoberta (dedo na frente) seria cortada — e segurar
        # a carta durante a oclusão é justamente o que o leitor existe para
        # fazer.
        if self._vistos:
            teto: Counter = Counter()
            for c in self._vistos:
                for code, n in c.items():
                    if n > teto[code]:
                        teto[code] = n
            por_codigo: dict[str, list[dict]] = {}
            for s in confirmed:
                rotulo = self._winner(s["votes"], s.get("label"))
                por_codigo.setdefault(rotulo, []).append(s)
            mantidos = []
            for code, slots in por_codigo.items():
                if len(slots) > teto[code]:
                    # `misses` antes do peso, como no `_corta` e pelo mesmo
                    # motivo: depois de o leque se mover, a vaga ÓRFÃ ainda é
                    # tão "forte" quanto a nova (leva os votos de quando a
                    # carta estava ali), e o desempate por peso ficaria no
                    # empate — mantendo justamente a que não corresponde a
                    # nenhuma carta no quadro.
                    slots = sorted(slots,
                                   key=lambda s: (s["misses"],
                                                  -self._weight(s["votes"]))
                                   )[:teto[code]]
                mantidos += slots
            confirmed = mantidos
        if self.max_slots is not None:
            confirmed = self._corta(confirmed, self.max_slots)
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
        self.ultimo_leque = []
        self._vistos.clear()
