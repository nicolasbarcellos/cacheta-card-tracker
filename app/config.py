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
    stable_frames: int = 10
    hand_absent_frames: int = 45  # ~3s sem ver a carta (com outras visíveis) = sai da mão
    # leitor do leque (votação temporal por posição)
    # medido no setup real: jitter da mesma carta entre frames = 3px (p95 8px)
    # e espaçamento mínimo entre cantos vizinhos = 47px. 30 dá folga de 3.7x
    # sobre o jitter e 1.6x de margem contra casar na vaga do vizinho.
    fan_match_dist: float = 30.0   # px: casar detecção à mesma vaga entre frames
    fan_window: int = 30           # frames recentes que votam por vaga
    fan_min_appear: int = 5        # aparições p/ uma vaga contar (mata fantasmas)
    fan_expire: int = 24           # frames de ausência p/ a vaga sumir. generoso
    #                                de propósito: segura a carta que pisca. quem
    #                                impede vaga órfã de duplicar agora é o teto
    #                                de vagas do FanReader (= hand_size)
    lock_frames: int = 12          # frames de 9 estável p/ TRAVAR a mão no overlay
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
