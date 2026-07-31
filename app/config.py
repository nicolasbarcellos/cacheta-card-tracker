from dataclasses import dataclass


@dataclass
class Config:
    # 2 webcams disponíveis. O índice 1 é a que enquadra o leque do jogador
    # (câmera da MÃO); a 0 sobra para o monte de descarte.
    discard_cam_index: int = 0
    hand_cam_index: int = 1
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
    # p95 (66px) praticamente empata com o menor espaçamento. O conserto real é
    # compensar o movimento GLOBAL do leque antes de casar as vagas (a mão
    # translada o leque inteiro junto, não cada carta em separado); enquanto
    # isso não existir, apoiar a mão reduz muito o jitter.
    fan_match_dist: float = 50.0   # px: casar detecção à mesma vaga entre frames
    fan_window: int = 30           # frames recentes que votam por vaga
    fan_min_appear: int = 5        # aparições p/ uma vaga contar (mata fantasmas)
    fan_expire: int = 24           # frames de ausência p/ a vaga sumir. generoso
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
    lock_frames: int = 12          # frames de 9 estável p/ TRAVAR a mão no overlay
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
