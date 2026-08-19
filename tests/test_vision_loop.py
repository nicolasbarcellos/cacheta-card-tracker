from app.cards import Card
from app.detector import Detection
from app.hand_reader import FanReader
from app.main import process_frame
from app.stable_hand import StableHand
from app.tracker import GameTracker


def det(code, conf=0.9, x=0):
    # caixas espalhadas na horizontal como um leque real (posições distintas)
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(x, 0, x + 10, 10))


def hand(*codes):
    return [det(c, x=i * 100) for i, c in enumerate(codes)]

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]


def make_hand_view():
    return FanReader(match_dist=45, window=10, min_appear=3, expire=6)


def make_lock():
    return StableHand(lock_frames=4)


def feed(n, cards, tracker, hv, lock):
    for _ in range(n):
        process_frame(cards, tracker, hv, lock)


def test_full_turn_emits_draw_then_discard():
    """Turno completo pela câmera da MÃO, sem a câmera do monte.

    A mão cresce de 9 para 10 (compra) e volta a 9 (descarte). É a mudança do
    leque que gera os dois eventos.
    """
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()

    feed(8, hand(*HAND9), tracker, hv, lock)
    assert tracker.events == []          # primeira leitura é só a referência

    feed(8, hand(*HAND9, "KC"), tracker, hv, lock)
    assert [e.type for e in tracker.events] == ["draw"]
    assert tracker.events[0].card.code == "KC"

    # Descarta o 9D: a mão volta a 9 cartas. Leva mais frames que a compra —
    # ao tirar uma carta do meio, as outras deslizam, e a vaga que era do 9D
    # precisa acumular votos da carta que passou a ocupá-la.
    resto = [c for c in HAND9 if c != "9D"] + ["KC"]
    feed(30, hand(*resto), tracker, hv, lock)
    assert [e.type for e in tracker.events] == ["draw", "discard"]
    assert tracker.events[1].card.code == "9D"


def test_card_bought_from_the_discard_pile_is_marked():
    """Ciclo real da cacheta: 9 -> 10 (compra) -> 9 (descarte) -> 10.

    A mão nunca passa por 8: compra-se ANTES de descartar. A exibição só
    aceita mão plausível (0, 9 ou 10), então uma leitura de 8 seria bagunça
    de transição e não uma jogada.
    """
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()

    feed(8, hand(*HAND9), tracker, hv, lock)
    # compra o KC -> 10 cartas
    feed(30, hand(*HAND9, "KC"), tracker, hv, lock)
    # descarta o 9D -> volta a 9
    nove = [c for c in HAND9 if c != "9D"] + ["KC"]
    feed(30, hand(*nove), tracker, hv, lock)
    # e compra o mesmo 9D de volta: veio do lixo
    feed(30, hand(*nove, "9D"), tracker, hv, lock)

    draws = [e for e in tracker.events if e.type == "draw"]
    assert [d.card.code for d in draws] == ["KC", "9D"]
    assert draws[0].source == "monte"
    assert draws[1].source == "lixo"


def test_hand_leaving_the_frame_is_not_nine_discards():
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()
    feed(8, hand(*HAND9), tracker, hv, lock)
    feed(30, [], tracker, hv, lock)      # jogador abaixou as cartas
    assert tracker.events == []


def test_locked_hand_shows_after_stable_nine():
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()
    feed(15, hand(*HAND9), tracker, hv, lock)
    codes = [c["code"] for c in tracker.state()["hand"]]
    assert sorted(codes) == sorted(HAND9)


def test_locked_hand_holds_through_flicker():
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()
    feed(15, hand(*HAND9), tracker, hv, lock)
    eight = HAND9[:-1]
    for _ in range(10):  # a 9ª carta pisca (some/volta)
        process_frame(hand(*eight), tracker, hv, lock)
        process_frame(hand(*HAND9), tracker, hv, lock)
    codes = [c["code"] for c in tracker.state()["hand"]]
    assert sorted(codes) == sorted(HAND9)  # segurou as 9
