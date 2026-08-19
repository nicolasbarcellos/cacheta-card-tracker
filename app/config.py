from dataclasses import dataclass


@dataclass
class Config:
    # UMA câmera: a webcam USB apontada para a mão. A interna do notebook,
    # que servia de preview do monte, saiu em 2026-08-19 — compra e descarte
    # deixaram de ser objetivo deste modelo e vão para outras câmeras.
    #
    # ATENÇÃO: o índice NÃO é fixo. O Windows renumera as câmeras ao
    # desconectar/reconectar o USB ou reiniciar — em 2026-08-04 a externa era a 1
    # e virou a 0, e o app passou a mostrar o rosto do jogador como "mão".
    # Sintoma: o preview "Câmera da mão" do painel mostra a câmera errada.
    # `scripts/check_cams.py` mostra o que cada índice está vendo.
    hand_cam_index: int = 0
    frame_width: int = 1920
    frame_height: int = 1080
    detect_imgsz: int = 1280  # resolução da inferência (cantos são pequenos)
    model_path: str = "models/cards.pt"
    min_confidence: float = 0.30  # baixo de propósito: a votação temporal
    #                               (FanReader) filtra o ruído; limiar alto
    #                               cortava cartas reais de confiança média
    confirm_confidence: float = 0.85
    # NMS agnóstico de classe DESLIGADO. Medido no setup real com um leque de
    # 4 quatros + 4 áses: ligado, ele funde caixas sobrepostas de classes
    # diferentes por frame e mantém só a mais confiante — jogando fora o
    # palpite que o FanReader existe para julgar (com tempo + confiança) e
    # suprimindo cartas VIZINHAS legítimas do leque apertado. Com ele ligado o
    # 4♥ e o 4♣ desapareciam da mão e as vizinhas duplicavam; com ele
    # desligado, o rótulo certo vence o voto ponderado em 8 das 9 vagas
    # (o 4♥ sai em 695 frames com confiança média 0.74).
    agnostic_nms: bool = False
    stable_frames: int = 10
    hand_absent_frames: int = 45  # ~3s sem ver a carta (com outras visíveis) = sai da mão
    # leitor do leque (votação temporal por posição)
    #
    # RE-MEDIDO em 2026-07-30, com o leque grande no quadro (que é o que o
    # modelo precisa para ler o pip) e segurado na mão:
    #   jitter da mesma carta = 29.5px médio, 66px p95   (era 3px / p95 8px)
    #   espaçamento entre vizinhas = 44px mín, 69px p05, 111px p50  (era 47px)
    #
    # O leque perto da câmera amplia o tremor da mão na mesma proporção em que
    # amplia a carta, então o jitter cresceu ~8x. Com 30px o raio ficava 2.2x
    # MENOR que o jitter p95: a mesma carta saía da própria vaga a cada tremor
    # e criava vaga nova — origem das vagas duplicadas e da instabilidade entre
    # travas sucessivas (a mesma mão dava 9/9 e depois 7/9).
    #
    # 50px atende o caso típico: acima do jitter médio (29.5) e abaixo do
    # espaçamento p05 (69). Não há valor que atenda os dois EXTREMOS — o jitter
    # p95 (66px) praticamente empata com o menor espaçamento. O movimento GLOBAL
    # do leque JÁ é compensado antes do casamento (`FanReader._estimate_shift`,
    # desde a542f75); o que este raio ainda precisa cobrir é só o movimento
    # RELATIVO entre cartas. Este comentário dizia que a compensação não existia
    # até 2026-08-12.
    #
    # Varrido contra a partida de 2026-08-12 (19 descartes): 60px deu 78,9% de
    # descartes contra 68,4% em 50px, com as compras em 100% nos dois. NÃO foi
    # alterado: a diferença são DUAS jogadas numa amostra de 19, e afinar num
    # único jogo é ajustar no conjunto que avalia. Refazer com mais partidas.
    # ATENÇÃO ao mexer nos contadores em FRAMES abaixo: eles são constantes de
    # TEMPO disfarçadas. Todos foram afinados contra ações físicas do jogador
    # (terminar de organizar o leque, a mão passar na frente, fechar o leque
    # para encaixar a carta), então o que vale é a duração — e a duração
    # depende do FPS, que ninguém tinha medido.
    #
    # MEDIDO em 2026-08-11 com o FpsMeter: 45 fps. O CLAUDE.md assumia ~15, e
    # a validação ao vivo de 2026-08-04 rodou a ~22 (o laço ainda gastava
    # metade da inferência na câmera do descarte). Ao desligar aquela detecção
    # o FPS dobrou e cada janela passou a durar METADE — desfazendo na prática
    # o 81847b8, que subiu lock_frames de 12 para 30 justamente porque 0,55s
    # era curto demais. Os valores abaixo são o DOBRO dos antigos, para
    # reproduzir as durações já validadas a 45 fps.
    fan_match_dist: float = 50.0   # px: casar detecção à mesma vaga entre frames
    fan_window: int = 60           # ~1,3s de votos por vaga (era 30 @ ~22fps)
    fan_min_appear: int = 10       # aparições p/ uma vaga contar (mata fantasmas)
    fan_expire: int = 48           # ~1,1s de ausência p/ a vaga sumir. generoso
    #                                de propósito: segura a carta que pisca. quem
    #                                impede vaga órfã de duplicar agora é o teto
    #                                de vagas do FanReader (= hand_size)
    # Quanto a carta concorrente precisa acumular a MAIS que a atual para
    # trocar o rótulo de uma vaga já estabelecida. Medido: com o modelo velho
    # a troca A♦/4♦ vinha com o errado ganhando por 2,28x sustentado ao longo
    # de 21 dos 30 frames da janela — margem nenhuma filtraria aquilo, era
    # defeito de modelo. Depois do retreino com peso nos ranks fracos (A subiu
    # para 96,5%, 4 para 96,6%) o erro virou RAJADA CURTA, e aí margem resolve.
    # Custo: uma troca de carta REAL demora ~22 frames (~1,5s) para aparecer,
    # porque a nova precisa empurrar a antiga para fora da janela de votos.
    fan_win_margin: float = 2.5
    # Zona morta nas bordas do quadro: uma detecção que encosta nela não pode
    # CRIAR vaga (votar numa vaga existente continua valendo). Carta que sai
    # pelo enquadramento tem o índice cortado, e o modelo palpita sobre meio
    # glifo. Medido na partida de 2026-08-11 — ver `FanReader._cortada`.
    #
    # 8 px é o MEIO de um platô medido contra a partida real: 2 a 14 px dão o
    # resultado idêntico e melhor (4 dos 5 fantasmas somem, 100% de acerto em
    # compras e descartes preservado); em 18 px começa a cortar carta legítima
    # e um descarte sai errado. 0 desliga.
    fan_borda: float = 8.0
    # Piso de peso, como FRAÇÃO da mediana das vagas, aplicado SÓ à vaga cujo
    # rótulo DUPLICA outra carta da mão. Abaixo dele ela não conta como carta.
    # Mata o fantasma que nasce de erro de classe: quando o modelo lê o A♥ como
    # A♦ por meio segundo, a mão sai com o A♥ (que ainda não expirou) mais dois
    # A♦ — dez cartas que nunca estiveram juntas em frame nenhum, e daí uma
    # compra e um descarte que não aconteceram. Ver `FanReader._recompute`.
    #
    # Varrido contra as DUAS partidas gravadas, re-detectadas com o modelo de
    # 18/08. Na de 12/08 o platô de 100%/100% é 0,6-0,7 (0,5 dá 95%/94,7% e
    # 0,8 volta a perder jogada); 0,6 é o que deixa menos fantasma. A de 11/08
    # fica em 100%/100% para qualquer valor de 0 a 0,8 — ou seja o piso não tem
    # custo lá. ATENÇÃO ao mexer: o platô é ESTREITO e cada jogada vale 5 pontos
    # numa amostra de 19; o mecanismo é sólido, o número é fraco. 0 desliga.
    fan_peso_min: float = 0.6
    # Frames com a MESMA leitura antes de trocar a mão exibida. Com 12 (~0,8s)
    # uma leitura errada durante a organização das cartas na mão durava tempo
    # suficiente para entrar — o jogador ainda estava acomodando o leque, com
    # os dedos por cima do índice, e o sistema já aceitava.
    #
    # 30 (~2s) usa a estabilidade como sinal de "terminei de organizar": não dá
    # para exigir 9 ou 10 cartas, porque nem sempre o leque está todo aberto,
    # mas enquanto a mão se mexe a leitura muda o tempo todo e não estabiliza.
    # Custo: compra e descarte demoram ~1,2s a mais para aparecer.
    #
    # 60 desde 2026-08-11: os 30 valiam ~1,4s a 22 fps e passaram a valer 0,7s
    # depois que o FPS dobrou — perto dos 0,55s que já tinham sido rejeitados.
    # Ver o bloco sobre FPS logo acima.
    #
    # 20 desde 2026-08-19, quando o objetivo passou a ser LER A MÃO e não mais
    # emitir compra/descarte. A espera longa existia para proteger o EVENTO:
    # um evento disparado em leitura tremida vira erro permanente no histórico,
    # enquanto uma mão exibida errada se corrige sozinha no frame seguinte.
    # Varrido contra a partida de 19/08 (5 min, 27 fps):
    #
    #   frames   atraso    carta vista fora da tela   trocas de mão
    #      60     2,54s              13,5%                 17
    #      45     1,93s               9,9%                 18
    #      30     1,28s               8,4%                 18
    #      20     0,86s               7,5%                 18   <-
    #      10     0,43s               8,0%                 24
    #
    # Ou seja: esperar mais não estava comprando acerto nenhum, só atraso —
    # e abaixo de 20 a tela começa a tremer (24 trocas para ~12 jogadas).
    lock_frames: int = 20
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
