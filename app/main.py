import threading

import uvicorn

from app.capture import CameraStream
from app.cards import Card
from app.config import config
from app.detector import CardDetector, draw_boxes, hand_codes, pick_top_card
from app.server import create_app
from app.stability import StabilityFilter
from app.tracker import GameTracker


def make_filters(stable_frames: int):
    return {"discard": StabilityFilter(stable_frames),
            "hand": StabilityFilter(stable_frames)}


def process_frame(detections_discard, detections_hand, filters, tracker):
    """Um passo do laço de visão. Puro: recebe detecções, atualiza o tracker."""
    top = pick_top_card(detections_discard)
    stable_top = filters["discard"].update(top.card.code if top else None)
    if stable_top:
        tracker.on_stable_top_card(Card.from_label(stable_top),
                                   confidence=top.confidence if top else 1.0)

    codes = hand_codes(detections_hand)
    stable_hand = filters["hand"].update(codes if codes else None)
    if stable_hand:
        tracker.on_stable_hand(frozenset(
            Card.from_label(c) for c in stable_hand))


def vision_loop(cams, detector, filters, tracker, annotated, running):
    while running.is_set():
        detections = {"discard": [], "hand": []}
        for name in detections:
            frame = cams[name].read()
            if frame is None:
                continue  # câmera ainda aquecendo; lista vazia vira None no filtro
            dets = detector.detect(frame)
            detections[name] = dets
            annotated[name] = draw_boxes(frame, dets)
        process_frame(detections["discard"], detections["hand"],
                      filters, tracker)


def main():
    tracker = GameTracker(hand_size=config.hand_size)
    filters = make_filters(config.stable_frames)
    annotated: dict = {}
    cams = {
        "discard": CameraStream(config.discard_cam_index,
                                config.frame_width, config.frame_height),
        "hand": CameraStream(config.hand_cam_index,
                             config.frame_width, config.frame_height),
    }
    detector = CardDetector(config.model_path, config.min_confidence)

    def reset_filters():
        filters["discard"].reset()
        filters["hand"].reset()

    app = create_app(tracker, annotated_frames=annotated,
                     on_new_round=reset_filters)

    running = threading.Event()
    running.set()
    thread = threading.Thread(
        target=vision_loop,
        args=(cams, detector, filters, tracker, annotated, running),
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
