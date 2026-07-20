from app.stable_hand import StableHand

NINE = ["2S", "6C", "9C", "9D", "AD", "AH", "AS", "JC", "QS"]


def feed(sh, cards, n):
    changed = False
    for _ in range(n):
        changed = sh.update(cards) or changed
    return changed


def test_locks_stable_nine():
    sh = StableHand(hand_size=9, lock_frames=12)
    assert feed(sh, NINE, 20) is True
    assert sorted(sh.cards) == sorted(NINE)


def test_flickering_ninth_card_holds_locked():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)                      # trava as 9
    locked = sorted(sh.cards)
    eight = [c for c in NINE if c != "AS"]
    # o A♠ pisca: some por alguns frames, volta, some...
    for _ in range(30):
        sh.update(eight)                    # A♠ ausente
        sh.update(NINE)                     # A♠ volta
    assert sorted(sh.cards) == locked       # continua mostrando as 9


def test_brief_dropout_does_not_unlock():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    for _ in range(5):                      # mão sai do quadro por pouco
        sh.update([])
    assert sorted(sh.cards) == sorted(NINE)  # segura


def test_does_not_auto_relock_holds_first_lock():
    # trava uma vez e segura: mesmo vendo um 9 diferente estável, NÃO troca
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    locked = sorted(sh.cards)
    new = [c for c in NINE if c != "QS"] + ["KH"]
    feed(sh, new, 40)
    assert sorted(sh.cards) == locked          # segurou a 1ª mão


def test_relock_after_button_picks_new_hand():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    new = [c for c in NINE if c != "QS"] + ["KH"]
    sh.force_relock()                          # apertou "Reler mão"
    feed(sh, new, 40)
    assert sorted(sh.cards) == sorted(new)


def test_transient_extra_card_does_not_change_lock():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    locked = sorted(sh.cards)
    # fantasma aparece por poucos frames (10 cartas), não estabiliza
    for _ in range(4):
        sh.update(NINE + ["3H"])
    assert sorted(sh.cards) == locked


def test_force_relock_allows_new_lock():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    sh.force_relock()
    new = [c for c in NINE if c != "2S"] + ["KD"]
    feed(sh, new, 40)
    assert sorted(sh.cards) == sorted(new)


def test_twins_two_of_same_code():
    sh = StableHand(hand_size=4, lock_frames=8)
    hand = ["7H", "7H", "9S", "KD"]
    feed(sh, hand, 15)
    assert sorted(sh.cards) == sorted(hand)   # duas 7H preservadas


def test_reset_clears_lock():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    sh.reset()
    assert sh.cards == []
