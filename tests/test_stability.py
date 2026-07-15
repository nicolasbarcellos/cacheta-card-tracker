from app.stability import StabilityFilter


def test_emits_after_n_consecutive_frames():
    f = StabilityFilter(frames_required=3)
    assert f.update("QS") is None
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_emits_only_once_per_value():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    assert f.update("QS") is None  # já emitido, não repete


def test_interruption_resets_count():
    f = StabilityFilter(frames_required=3)
    f.update("QS")
    f.update("QS")
    f.update("7D")  # mão passou na frente, viu outra coisa
    assert f.update("QS") is None
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_none_resets_count():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    f.update(None)
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_new_value_can_emit_after_previous():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    f.update("7D")
    assert f.update("7D") == "7D"


def test_reset_allows_same_value_again():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    f.reset()
    f.update("QS")
    assert f.update("QS") == "QS"
