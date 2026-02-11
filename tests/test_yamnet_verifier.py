import numpy as np

from baby_cry_detection.monitor.backends.yamnet_verifier import YamnetVerifierBackend


def test_aggregate_scores_applies_non_cry_suppression():
    class_names = ["Baby cry, infant cry", "Cat", "Speech", "Vacuum cleaner"]
    mean_scores = np.array([0.62, 0.10, 0.55, 0.15], dtype=np.float32)

    result = YamnetVerifierBackend._aggregate_scores(mean_scores, class_names, non_cry_weight=1.0)

    assert result.baby_score < 0.62
    assert result.cat_score >= 0.55


def test_aggregate_scores_keeps_baby_when_clear():
    class_names = ["Baby cry, infant cry", "Cat", "Speech"]
    mean_scores = np.array([0.81, 0.12, 0.10], dtype=np.float32)

    result = YamnetVerifierBackend._aggregate_scores(mean_scores, class_names, non_cry_weight=1.0)

    assert result.baby_score > 0.7
    assert result.cat_score < 0.2
