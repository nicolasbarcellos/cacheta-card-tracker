from app.config import config


def test_config_defaults():
    assert config.hand_size == 9
    assert config.min_confidence == 0.75
    assert config.stable_frames == 10
