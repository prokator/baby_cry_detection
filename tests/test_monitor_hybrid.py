import numpy as np

from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.monitor.backends.hybrid import HybridDetectionBackend


class _Primary:
    def score(self, audio_window, sample_rate):
        del audio_window, sample_rate
        return DetectionResult(primary_score=0.9, baby_score=0.7, cat_score=0.2)


class _Verifier:
    def score(self, audio_window, sample_rate):
        del audio_window, sample_rate
        return DetectionResult(primary_score=0.1, baby_score=0.8, cat_score=0.1)


def test_hybrid_uses_primary_and_verifier():
    backend = HybridDetectionBackend(primary_backend=_Primary(), verifier_backend=_Verifier())
    result = backend.score(audio_window=np.zeros(32, dtype=np.float32), sample_rate=16000)

    assert result.primary_score == 0.9
    assert result.baby_score == 0.8
    assert result.cat_score == 0.1
