from fastapi.testclient import TestClient

from app.cards import Card
from app.server import create_app
from app.tracker import GameTracker


def make_client():
    tracker = GameTracker()
    app = create_app(tracker)
    return tracker, TestClient(app)


def test_state_endpoint():
    tracker, client = make_client()
    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.json() == {"draw": None, "discard": None, "hand": [],
                           "paused": False, "events": []}


def test_correct_endpoint():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    event_id = tracker.events[0].id
    resp = client.post("/api/correct", json={"event_id": event_id, "card": "QH"})
    assert resp.status_code == 200
    assert tracker.events[0].card.code == "QH"


def test_correct_invalid_card_returns_422():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    resp = client.post("/api/correct",
                       json={"event_id": tracker.events[0].id, "card": "ZZ"})
    assert resp.status_code == 422


def test_correct_unknown_event_returns_404():
    _, client = make_client()
    resp = client.post("/api/correct", json={"event_id": 99, "card": "QS"})
    assert resp.status_code == 404


def test_undo_and_pause_and_new_round():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    assert client.post("/api/undo").status_code == 200
    assert tracker.events == []
    assert client.post("/api/pause", json={"paused": True}).status_code == 200
    assert tracker.paused is True
    assert client.post("/api/new-round").status_code == 200


def test_websocket_sends_state_on_connect():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert data["type"] == "state"
        assert data["discard"]["card"]["code"] == "QS"


def test_correct_hand_endpoint():
    from app.cards import Card
    tracker, client = make_client()
    tracker.set_hand_display([Card.from_label(x) for x in
                              ["AS", "2S", "9C", "9C", "6C"]])
    # posição 3 é 9C errado -> corrige para 9S
    resp = client.post("/api/correct-hand", json={"index": 3, "card": "9S"})
    assert resp.status_code == 200
    codes = [c["code"] for c in tracker.state()["hand"]]
    assert "9S" in codes


def test_correct_hand_invalid_index():
    _, client = make_client()
    resp = client.post("/api/correct-hand", json={"index": 5, "card": "9S"})
    assert resp.status_code == 404


def test_correct_hand_invalid_card():
    from app.cards import Card
    tracker, client = make_client()
    tracker.set_hand_display([Card.from_label("AS")])
    resp = client.post("/api/correct-hand", json={"index": 0, "card": "ZZ"})
    assert resp.status_code == 422
