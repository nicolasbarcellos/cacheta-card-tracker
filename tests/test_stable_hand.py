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


def test_follows_a_new_stable_hand_without_a_button():
    # acompanha sozinho: um conjunto diferente e estavel substitui o exibido
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    new = [c for c in NINE if c != "QS"] + ["KH"]
    feed(sh, new, 20)
    assert sorted(sh.cards) == sorted(new)


def test_follows_the_tenth_card_of_a_draw():
    """O caso da compra: 9 na mao, o jogador puxa uma e ficam 10.

    A exibicao tem de mostrar as 10 sozinha. Antes exigia exatamente
    hand_size, entao a decima carta era invisivel ate alguem clicar em
    "Reler mao" - e nem assim, porque o clique tambem so aceitava 9.
    """
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    assert len(sh.cards) == 9
    dez = NINE + ["KH"]
    feed(sh, dez, 20)
    assert len(sh.cards) == 10
    assert sorted(sh.cards) == sorted(dez)


def test_back_to_nine_after_the_discard():
    # e depois do descarte volta a 9, tambem sozinho
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE + ["KH"], 25)
    assert len(sh.cards) == 10
    feed(sh, NINE, 25)
    assert sorted(sh.cards) == sorted(NINE)


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


def test_lock_keeps_the_left_to_right_order():
    """A ordem entregue pelo FanReader (esquerda -> direita) tem de sobreviver.

    Antes o candidato saía de `sorted(counts)`, ou seja, em ordem alfabética
    de código — a mão travada aparecia embaralhada em relação ao leque.
    """
    sh = StableHand(hand_size=5, lock_frames=6)
    mao = ["QS", "2H", "KD", "AC", "7S"]     # fora de ordem alfabética
    feed(sh, mao, 12)
    assert sh.cards == mao


def test_reorder_does_not_reset_the_stability_count():
    # tremor troca duas cartas de lugar: e a MESMA mao, nao pode atrasar a trava
    sh = StableHand(hand_size=4, lock_frames=6)
    a = ["AS", "2H", "3D", "4C"]
    b = ["2H", "AS", "3D", "4C"]
    for i in range(8):
        sh.update(a if i % 2 else b)
    assert sorted(sh.cards) == sorted(a)


def test_incomplete_reading_does_not_replace_the_hand():
    """Leitura estavel de 7 cartas nao substitui a mao de 9.

    No ato de por ou tirar uma carta, a mao passa na frente e a leitura desce
    a 6-8 por um segundo. Mostrar isso e o que dava a sensacao de o sistema
    trocar as cartas sozinho.
    """
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    assert len(sh.cards) == 9
    feed(sh, NINE[:7], 40)                  # leitura incompleta, mas estavel
    assert sorted(sh.cards) == sorted(NINE)  # segurou a mao boa


def test_incomplete_reading_then_a_real_hand_updates():
    # depois da bagunca, uma mao inteira de novo e aceita normalmente
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    feed(sh, NINE[:7], 20)                  # transicao bagunçada
    nova = [c for c in NINE if c != "QS"] + ["KH"]
    feed(sh, nova, 40)
    assert sorted(sh.cards) == sorted(nova)


def test_empties_when_the_hand_leaves_for_good():
    # cartas fora do quadro por tempo suficiente: a mao exibida zera sozinha
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    assert len(sh.cards) == 9
    feed(sh, [], 40)
    assert sh.cards == []


def test_reset_clears_lock():
    sh = StableHand(hand_size=9, lock_frames=12)
    feed(sh, NINE, 20)
    sh.reset()
    assert sh.cards == []
