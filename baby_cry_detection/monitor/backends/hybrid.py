from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from baby_cry_detection.monitor.backends.base import DetectionResult

if TYPE_CHECKING:
    from baby_cry_detection.monitor.backends.existing_model import ExistingModelBackend
    from baby_cry_detection.monitor.backends.yamnet_verifier import YamnetVerifierBackend


class HybridDetectionBackend:
    """Primary detector + YAMNet-style verification layer."""

    def __init__(
        self,
        primary_backend: ExistingModelBackend,
        verifier_backend: YamnetVerifierBackend | None,
    ) -> None:
        self.primary_backend = primary_backend
        self.verifier_backend = verifier_backend

    def score(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        primary = self.primary_backend.score(audio_window=audio_window, sample_rate=sample_rate)
        if self.verifier_backend is None:
            return primary

        verifier = self.verifier_backend.score(audio_window=audio_window, sample_rate=sample_rate)
        baby_score = verifier.baby_score if verifier.baby_score > 0 else primary.baby_score
        cat_score = verifier.cat_score if verifier.cat_score > 0 else primary.cat_score
        return DetectionResult(
            primary_score=primary.primary_score,
            baby_score=baby_score,
            cat_score=cat_score,
        )
