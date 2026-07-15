from dataclasses import dataclass

RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = {"S": "espadas", "H": "copas", "D": "ouros", "C": "paus"}
RANK_NAMES = {"A": "ás", "J": "valete", "Q": "dama", "K": "rei"}


class InvalidCardLabel(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @classmethod
    def from_label(cls, raw: str) -> "Card":
        label = raw.strip().upper()
        rank, suit = label[:-1], label[-1:]
        if rank not in RANKS or suit not in SUITS:
            raise InvalidCardLabel(raw)
        return cls(rank, suit)

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def asset(self) -> str:
        return f"{self.code}.png"

    @property
    def display(self) -> str:
        return f"{RANK_NAMES.get(self.rank, self.rank)} de {SUITS[self.suit]}"

    def to_dict(self) -> dict:
        return {"code": self.code, "asset": self.asset, "display": self.display}
