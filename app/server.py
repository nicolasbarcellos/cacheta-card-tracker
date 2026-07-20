import asyncio
import queue
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.cards import Card, InvalidCardLabel
from app.tracker import GameTracker

ROOT = Path(__file__).resolve().parent.parent


class CorrectBody(BaseModel):
    event_id: int
    card: str


class PauseBody(BaseModel):
    paused: bool


class CorrectHandBody(BaseModel):
    index: int
    card: str


def create_app(tracker: GameTracker,
               annotated_frames: dict | None = None,
               on_new_round=None,
               on_relock=None) -> FastAPI:
    app = FastAPI()
    annotated_frames = annotated_frames if annotated_frames is not None else {}
    clients: set[WebSocket] = set()
    changes: queue.Queue = queue.Queue()

    # o tracker roda na thread de visão; o WS roda no event loop.
    # on_change enfileira; um task assíncrono drena a fila e faz broadcast.
    tracker.on_change = lambda: changes.put(True)

    async def broadcast_state():
        payload = {"type": "state", **tracker.state()}
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                clients.discard(ws)

    @app.on_event("startup")
    async def start_broadcaster():
        async def pump():
            while True:
                try:
                    changes.get_nowait()
                    while not changes.empty():  # colapsa rajadas
                        changes.get_nowait()
                    await broadcast_state()
                except queue.Empty:
                    await asyncio.sleep(0.05)
        asyncio.create_task(pump())

    @app.get("/")
    async def index():
        return RedirectResponse("/painel")

    @app.get("/overlay")
    async def overlay():
        return FileResponse(ROOT / "web" / "overlay" / "index.html")

    @app.get("/overlay/mao")
    async def overlay_mao():
        return FileResponse(ROOT / "web" / "overlay" / "mao.html")

    @app.get("/painel")
    async def painel():
        return FileResponse(ROOT / "web" / "painel" / "index.html")

    @app.get("/api/state")
    async def get_state():
        return tracker.state()

    @app.post("/api/correct")
    async def correct(body: CorrectBody):
        try:
            card = Card.from_label(body.card)
        except InvalidCardLabel:
            raise HTTPException(422, f"carta inválida: {body.card}")
        if not tracker.correct_event(body.event_id, card):
            raise HTTPException(404, f"evento {body.event_id} não existe")
        return {"ok": True}

    @app.post("/api/correct-hand")
    async def correct_hand(body: CorrectHandBody):
        try:
            card = Card.from_label(body.card)
        except InvalidCardLabel:
            raise HTTPException(422, f"carta inválida: {body.card}")
        if not tracker.correct_hand_card(body.index, card):
            raise HTTPException(404, f"posição {body.index} inválida")
        return {"ok": True}

    @app.post("/api/undo")
    async def undo():
        tracker.undo_last()
        return {"ok": True}

    @app.post("/api/new-round")
    async def new_round():
        tracker.new_round()
        if on_new_round:
            on_new_round()
        return {"ok": True}

    @app.post("/api/relock")
    async def relock():
        # re-lê a mão travada (após descartar/comprar): o próximo 9 estável trava
        if on_relock:
            on_relock()
        return {"ok": True}

    @app.post("/api/pause")
    async def pause(body: PauseBody):
        tracker.set_paused(body.paused)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        clients.add(ws)
        try:
            await ws.send_json({"type": "state", **tracker.state()})
            while True:
                await ws.receive_text()  # mantém a conexão viva
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    preview_cache: dict[str, tuple[float, bytes]] = {}

    def _encode_preview(cam: str) -> bytes | None:
        frame = annotated_frames.get(cam)
        if frame is None:
            return None
        h, w = frame.shape[:2]
        if w > 960:  # preview não precisa da resolução da detecção
            frame = cv2.resize(frame, (960, int(h * 960 / w)))
        ok, jpg = cv2.imencode(".jpg", frame,
                               [cv2.IMWRITE_JPEG_QUALITY, 75])
        return jpg.tobytes() if ok else None

    @app.get("/stream/{cam}")
    async def stream(cam: str):
        async def frames():
            while True:
                # cache compartilhado entre abas; encode fora do event loop
                cached = preview_cache.get(cam)
                now = asyncio.get_event_loop().time()
                if cached is None or now - cached[0] > 0.12:
                    data = await asyncio.to_thread(_encode_preview, cam)
                    if data:
                        preview_cache[cam] = (now, data)
                        cached = preview_cache[cam]
                if cached:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + cached[1] + b"\r\n")
                await asyncio.sleep(0.12)
        return StreamingResponse(
            frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    for mount, folder in (("/static", "web"), ("/assets", "assets")):
        path = ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        app.mount(mount, StaticFiles(directory=path), name=folder)

    return app
