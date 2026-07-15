from app.hand_view import HandView


def f(*codes):
    return frozenset(codes)


def test_card_enters_after_appear_frames():
    hv = HandView(appear_frames=3, absent_frames=5)
    assert hv.update(f("QS")) is False
    assert hv.update(f("QS")) is False
    assert hv.update(f("QS")) is True
    assert hv.cards == {"QS"}


def test_flicker_does_not_enter():
    hv = HandView(appear_frames=3, absent_frames=5)
    hv.update(f("QS"))
    hv.update(f())        # sumiu tudo: congela e zera candidatos
    hv.update(f("QS"))
    assert hv.update(f("QS")) is False  # recomeçou a contagem
    assert hv.cards == set()


def test_phantom_expires_while_others_visible():
    hv = HandView(appear_frames=2, absent_frames=3)
    hv.update(f("QS", "4S"))
    hv.update(f("QS", "4S"))            # ambas entram
    assert hv.cards == {"QS", "4S"}
    for _ in range(3):                   # 4S some, QS continua visível
        hv.update(f("QS"))
    assert hv.cards == {"QS"}


def test_lowered_hand_freezes_everything():
    hv = HandView(appear_frames=2, absent_frames=3)
    hv.update(f("QS", "4S"))
    hv.update(f("QS", "4S"))
    for _ in range(10):                  # mão fora do quadro
        assert hv.update(f()) is False
    assert hv.cards == {"QS", "4S"}      # nada expira sem detecções


def test_absence_counter_resets_when_seen_again():
    hv = HandView(appear_frames=2, absent_frames=4)
    hv.update(f("QS", "2H"))
    hv.update(f("QS", "2H"))
    hv.update(f("QS"))                   # 2H ausente 1
    hv.update(f("QS"))                   # 2H ausente 2
    hv.update(f("QS", "2H"))             # 2H reapareceu: zera
    hv.update(f("QS"))
    hv.update(f("QS"))
    hv.update(f("QS"))
    assert "2H" in hv.cards              # 3 < 4 ausências consecutivas


def test_reset_clears_all():
    hv = HandView(appear_frames=1, absent_frames=2)
    hv.update(f("QS"))
    hv.reset()
    assert hv.cards == set()
