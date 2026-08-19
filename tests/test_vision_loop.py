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


def test_o_laco_nao_emite_mais_compra_nem_descarte():
    """Escopo de 2026-08-19: este modelo LE A MAO, e so.

    Compra e descarte viraram responsabilidade de outros modelos, com outras
    cameras. `tracker.on_hand_changed` continua existindo e testado (ver
    tests/test_tracker_*), mas o laco de visao nao o chama mais — mostrar aqui
    um palpite que este modelo nao faz seria mentira na tela.
    """
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()

    feed(8, hand(*HAND9), tracker, hv, lock)
    feed(30, hand(*HAND9, "KC"), tracker, hv, lock)          # "compra"
    feed(30, hand(*[c for c in HAND9 if c != "9D"], "KC"), tracker, hv, lock)
    assert tracker.events == []


def test_a_mao_exibida_acompanha_a_ordem_do_leque():
    """A carta encaixada no MEIO tem de aparecer no meio.

    A ordem vinha congelada do instante da trava, e a carta ausente naquele
    frame ia para o FIM da lista — onde ficava mesmo depois de reaparecer no
    lugar certo. Medido numa partida real: 16,9% dos frames com a mao certa
    tinham a ordem errada.
    """
    tracker = GameTracker()
    hv, lock = make_hand_view(), make_lock()
    feed(15, hand(*HAND9), tracker, hv, lock)

    # KC entra entre a 3a e a 4a carta (x=250, entre 200 e 300)
    com_kc = [det(c, x=i * 100) for i, c in enumerate(HAND9)]
    com_kc.insert(3, det("KC", x=250))
    feed(30, com_kc, tracker, hv, lock)

    codes = [c["code"] for c in tracker.state()["hand"]]
    assert codes.index("KC") == 3, codes


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
