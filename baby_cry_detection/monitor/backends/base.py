from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class DetectionResult:
    primary_score: float
    baby_score: float
    cat_score: float


class DetectionBackend(Protocol):
    def score(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        raise NotImplementedError
