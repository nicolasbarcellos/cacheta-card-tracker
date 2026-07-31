import threading

import uvicorn

from app.capture import CameraStream
from app.cards import Card
from app.config import config
from app.detector import CardDetector, draw_boxes, hand_instances
from app.hand_reader import FanReader
from app.server import create_app
from app.stable_hand import StableHand
from app.tracker import GameTracker


def log_lock(hand_view, hand_lock):
    """Imprime o que o leitor viu quando a mão exibida mudou.

    Só imprime na mudança, então não polui a saída — e é o único jeito de
    saber, depois do fato, POR QUE uma carta saiu errada: rótulo repetido em
    posições distintas (o modelo leu duas cartas como a mesma) x duas vagas
    no mesmo lugar (o casamento por posição se perdeu).
    """
    print(f"\n=== mão do jogador: {' '.join(hand_lock.cards)}", flush=True)
    for i, s in enumerate(hand_view.slots_debug()):
        top = "  ".join(f"{code}={peso}" for code, peso in s["top"])
        print(f"  vaga {i}: x={s['x']:4d} y={s['y']:4d} "
              f"n={s['n']:3d} miss={s['misses']:2d}  {top}", flush=True)


def process_frame(detections_hand, tracker, hand_view, hand_lock):
    """Um passo do laço de visão. Puro: recebe detecções, atualiza o tracker.

    Compra e descarte saem os DOIS da câmera da mão, pela mudança do leque:
    cresceu uma carta = compra, encolheu uma = descarte. A câmera do monte não
    gera evento — se gerasse, o descarte sairia duplicado (uma vez pela mão,
    outra pelo monte).
    """
    # FanReader = leitura ao vivo (votada por posição); StableHand = histerese
    hand_view.update(hand_instances(detections_hand))
    if hand_lock.update(hand_view.cards):
        cards = [Card.from_label(c) for c in hand_lock.cards]
        tracker.set_hand_display(cards)
        tracker.on_hand_changed(cards)
        log_lock(hand_view, hand_lock)


def vision_loop(cams, detector, tracker, annotated, running,
                hand_view, hand_lock):
    while running.is_set():
        detections = {"discard": [], "hand": []}
        for name in detections:
            frame = cams[name].read()
            if frame is None:
                continue  # câmera ainda aquecendo
            dets = detector.detect(frame)
            detections[name] = dets
            annotated[name] = draw_boxes(frame, dets)
        # a câmera do monte continua sendo lida e anotada para o preview do
        # painel, mas não alimenta mais evento nenhum
        process_frame(detections["hand"], tracker, hand_view, hand_lock)


def main():
    tracker = GameTracker(hand_size=config.hand_size)
    hand_view = FanReader(match_dist=config.fan_match_dist,
                          window=config.fan_window,
                          min_appear=config.fan_min_appear,
                          expire=config.fan_expire,
                          # +1: a mão passa por 10 cartas no instante da
                          # compra e o jogador espera ver as 10. O teto ainda
                          # existe para matar vaga espúria — só subiu um.
                          max_slots=config.hand_size + 1,
                          win_margin=config.fan_win_margin)
    hand_lock = StableHand(hand_size=config.hand_size,
                           lock_frames=config.lock_frames)
    annotated: dict = {}
    cams = {
        "discard": CameraStream(config.discard_cam_index,
                                config.frame_width, config.frame_height),
        "hand": CameraStream(config.hand_cam_index,
                             config.frame_width, config.frame_height),
    }
    detector = CardDetector(config.model_path, config.min_confidence,
                            imgsz=config.detect_imgsz,
                            agnostic_nms=config.agnostic_nms)

    def reset_filters():
        hand_view.reset()
        hand_lock.reset()

    app = create_app(tracker, annotated_frames=annotated,
                     on_new_round=reset_filters,
                     on_relock=hand_lock.force_relock)

    running = threading.Event()
    running.set()
    thread = threading.Thread(
        target=vision_loop,
        args=(cams, detector, tracker, annotated, running,
              hand_view, hand_lock),
        daemon=True)
    thread.start()

    print(f"overlay: http://{config.server_host}:{config.server_port}/overlay")
    print(f"painel:  http://{config.server_host}:{config.server_port}/painel")
    try:
        uvicorn.run(app, host=config.server_host, port=config.server_port)
    finally:
        running.clear()
        for cam in cams.values():
            cam.stop()


if __name__ == "__main__":
    main()
