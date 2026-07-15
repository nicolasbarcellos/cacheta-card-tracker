"""Demo: simula uma partida para visualizar o overlay e o painel sem webcam.

Sobe o servidor real e, em background, joga turnos fake a cada poucos
segundos: compra uma carta (às vezes do lixo), depois descarta uma.
Rode e abra http://127.0.0.1:8000/overlay e http://127.0.0.1:8000/painel
"""
import random
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from app.cards import RANKS, SUITS, Card  # noqa: E402
from app.server import create_app  # noqa: E402
from app.tracker import GameTracker  # noqa: E402

tracker = GameTracker()
app = create_app(tracker)


def simulate():
    deck = [Card.from_label(f"{r}{s}") for r in RANKS for s in SUITS]
    random.shuffle(deck)

    time.sleep(2)
    hand = {deck.pop() for _ in range(9)}
    tracker.on_stable_hand(frozenset(hand))
    top_lixo = None

    while len(deck) > 1:
        time.sleep(4)
        # 30% das vezes compra do lixo (a última carta descartada)
        if top_lixo is not None and random.random() < 0.3:
            drawn = top_lixo
            top_lixo = None
        else:
            drawn = deck.pop()
        hand.add(drawn)
        tracker.on_stable_hand(frozenset(hand))

        time.sleep(2)
        discarded = random.choice(sorted(hand, key=lambda c: c.code))
        hand.remove(discarded)
        tracker.on_stable_top_card(discarded)
        tracker.on_stable_hand(frozenset(hand))
        top_lixo = discarded

    print("baralho acabou — demo encerrada (servidor continua de pé)")


threading.Thread(target=simulate, daemon=True).start()
print("overlay: http://127.0.0.1:8000/overlay")
print("painel:  http://127.0.0.1:8000/painel")
uvicorn.run(app, host="127.0.0.1", port=8000)
