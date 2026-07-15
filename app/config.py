from dataclasses import dataclass


@dataclass
class Config:
    # só existe 1 webcam (MX Brio, índice 0): por ora ela é a câmera da MÃO;
    # o descarte fica sem câmera até chegar a segunda
    discard_cam_index: int = 1
    hand_cam_index: int = 0
    frame_width: int = 1280
    frame_height: int = 720
    model_path: str = "models/cards.pt"
    min_confidence: float = 0.75
    confirm_confidence: float = 0.85
    stable_frames: int = 10
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
