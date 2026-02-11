from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.monitor.config import MonitorConfig
from baby_cry_detection.monitor.decision import passes_verifier


def _config():
    return MonitorConfig(
        telegram_bot_token="t",
        telegram_chat_id="c",
        baby_threshold=0.45,
        cat_weight=1.0,
        margin_threshold=0.15,
        cat_suppress_threshold=0.45,
    )


def test_passes_verifier_true():
    result = DetectionResult(primary_score=0.8, baby_score=0.8, cat_score=0.2)
    assert passes_verifier(_config(), result)


def test_passes_verifier_false_on_cat_dominance():
    result = DetectionResult(primary_score=0.8, baby_score=0.4, cat_score=0.8)
    assert not passes_verifier(_config(), result)
