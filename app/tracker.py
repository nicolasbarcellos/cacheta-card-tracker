from dataclasses import dataclass

from app.cards import Card
from app.config import config


@dataclass
class Event:
    id: int
    type: str  # "draw" | "discard"
    card: Card
    source: str | None = None  # "monte" | "lixo" (apenas draw)
    confirmed: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "card": self.card.to_dict(),
            "source": self.source,
            "confirmed": self.confirmed,
        }


class GameTracker:
    """Estado do jogo: transforma detecções estáveis em eventos draw/discard."""

    def __init__(self, hand_size: int = 9, on_change=None):
        self.hand_size = hand_size
        self.on_change = on_change or (lambda: None)
        self.paused = False
        self.events: list[Event] = []
        self._next_id = 1
        self._hand_ref: frozenset[Card] | None = None
        self._top_discard: Card | None = None
        self._discard_history: set[Card] = set()

    def _emit(self, type_: str, card: Card, source=None, confidence=1.0):
        event = Event(
            id=self._next_id,
            type=type_,
            card=card,
            source=source,
            confirmed=confidence >= config.confirm_confidence,
        )
        self._next_id += 1
        self.events.append(event)
        self.on_change()

    def on_stable_top_card(self, card: Card, confidence: float = 1.0):
        if self.paused or card == self._top_discard:
            return
        if card in self._discard_history:
            # topo antigo reapareceu (compraram do lixo) — não é descarte novo
            self._top_discard = card
            return
        self._top_discard = card
        self._discard_history.add(card)
        self._emit("discard", card, confidence=confidence)
