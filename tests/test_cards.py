import pytest

from app.cards import Card, InvalidCardLabel


def test_from_label_simple():
    card = Card.from_label("QS")
    assert card.rank == "Q"
    assert card.suit == "S"
    assert card.code == "QS"


def test_from_label_ten_and_lowercase():
    card = Card.from_label("10h")
    assert card.code == "10H"


def test_from_label_invalid():
    with pytest.raises(InvalidCardLabel):
        Card.from_label("ZZ")
    with pytest.raises(InvalidCardLabel):
        Card.from_label("JOKER")


def test_asset_and_display():
    card = Card.from_label("AD")
    assert card.asset == "AD.png"
    assert card.display == "ás de ouros"
    assert Card.from_label("7C").display == "7 de paus"


def test_to_dict():
    d = Card.from_label("KH").to_dict()
    assert d == {"code": "KH", "asset": "KH.png", "display": "rei de copas"}


def test_equality_and_hash():
    assert Card.from_label("2S") == Card.from_label("2s")
    assert len({Card.from_label("2S"), Card.from_label("2s")}) == 1
