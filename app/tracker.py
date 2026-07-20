from dataclasses import dataclass

from app.cards import RANKS, SUITS, Card
from app.config import config

_SUIT_ORDER = list(SUITS)


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
        self.hand_view: list[Card] = []

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

    def set_hand_display(self, cards: list[Card]):
        """Atualiza a mão exibida (decisão de quem entra/sai é do HandView)."""
        if self.paused:
            return
        as_list = sorted(cards, key=lambda c: (_SUIT_ORDER.index(c.suit),
                                               RANKS.index(c.rank)))
        if as_list != self.hand_view:
            self.hand_view = as_list
            self.on_change()

    def correct_hand_card(self, index: int, card: Card) -> bool:
        """Corrige manualmente uma carta da mão travada (clique no painel)."""
        if not 0 <= index < len(self.hand_view):
            return False
        self.hand_view[index] = card
        self.hand_view = sorted(self.hand_view,
                                key=lambda c: (_SUIT_ORDER.index(c.suit),
                                               RANKS.index(c.rank)))
        self.on_change()
        return True

    def on_stable_hand(self, cards: frozenset[Card]):
        if self.paused or not cards:
            return
        if self._hand_ref is None:
            if len(cards) == self.hand_size:
                self._hand_ref = cards
                self.on_change()
            return
        new = cards - self._hand_ref
        if len(cards) == self.hand_size + 1 and len(new) == 1:
            (card,) = new
            source = "monte"
            if card in self._discard_history:
                source = "lixo"
                self._discard_history.discard(card)
                if self._top_discard == card:
                    self._top_discard = None
            self._hand_ref = cards
            self._emit("draw", card, source=source)
        elif len(cards) == self.hand_size:
            self._hand_ref = cards
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

    def correct_event(self, event_id: int, card: Card) -> bool:
        event = next((e for e in self.events if e.id == event_id), None)
        if event is None:
            return False
        if event.type == "discard":
            self._discard_history.discard(event.card)
            self._discard_history.add(card)
            if self._top_discard == event.card:
                self._top_discard = card
        event.card = card
        event.confirmed = True
        self.on_change()
        return True

    def undo_last(self) -> bool:
        if not self.events:
            return False
        event = self.events.pop()
        if event.type == "discard":
            self._discard_history.discard(event.card)
            if self._top_discard == event.card:
                self._top_discard = None
        self.on_change()
        return True

    def new_round(self):
        self.events.clear()
        self._hand_ref = None
        self._top_discard = None
        self._discard_history.clear()
        self.hand_view = []
        self.on_change()

    def set_paused(self, paused: bool):
        self.paused = paused
        self.on_change()

    def state(self) -> dict:
        def last(type_):
            for e in reversed(self.events):
                if e.type == type_:
                    return e.to_dict()
            return None

        return {
            "draw": last("draw"),
            "discard": last("discard"),
            "hand": [c.to_dict() for c in self.hand_view],
            "paused": self.paused,
            "events": [e.to_dict() for e in reversed(self.events[-20:])],
        }
