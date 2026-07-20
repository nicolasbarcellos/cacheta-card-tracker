from dataclasses import dataclass


@dataclass
class Config:
    # só existe 1 webcam (MX Brio, índice 0): por ora ela é a câmera da MÃO;
    # o descarte fica sem câmera até chegar a segunda
    discard_cam_index: int = 1
    hand_cam_index: int = 0
    frame_width: int = 1920
    frame_height: int = 1080
    detect_imgsz: int = 1280  # resolução da inferência (cantos são pequenos)
    model_path: str = "models/cards.pt"
    min_confidence: float = 0.75
    confirm_confidence: float = 0.85
    stable_frames: int = 10
    hand_absent_frames: int = 45  # ~3s sem ver a carta (com outras visíveis) = sai da mão
    # leitor do leque (votação temporal por posição)
    fan_match_dist: float = 45.0   # px: casar detecção à mesma vaga entre frames
    fan_window: int = 25           # frames recentes que votam por vaga
    fan_min_appear: int = 8        # aparições p/ uma vaga contar (mata fantasmas)
    fan_expire: int = 18           # frames de ausência p/ a vaga sumir
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
