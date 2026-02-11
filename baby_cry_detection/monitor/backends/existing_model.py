from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.rpi_methods.feature_engineer import FeatureEngineer


class ExistingModelBackend:
    """
    Lightweight baseline wrapper for the existing detector path.
    This placeholder uses RMS energy and zero-crossing heuristics until
    the legacy serialized model is wired into runtime loading.
    """

    def __init__(self, model_path: str = "") -> None:
        self.model = None
        if model_path:
            path = Path(model_path)
            if path.exists():
                with path.open("rb") as fp:
                    self.model = pickle.load(fp)

    def score(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        if audio_window.size == 0:
            return DetectionResult(primary_score=0.0, baby_score=0.0, cat_score=0.0)

        if self.model is not None:
            return self._score_with_model(audio_window=audio_window, sample_rate=sample_rate)

        rms = float(np.sqrt(np.mean(np.square(audio_window))))
        zcr = float(np.mean(np.abs(np.diff(np.sign(audio_window))) > 0))

        primary_score = min(1.0, max(0.0, 2.5 * rms + 0.25 * zcr))
        baby_score = min(1.0, max(0.0, 2.2 * rms + 0.15 * zcr))
        cat_score = min(1.0, max(0.0, 0.8 * zcr + 0.2 * rms))
        return DetectionResult(primary_score=primary_score, baby_score=baby_score, cat_score=cat_score)

    def _score_with_model(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        import librosa

        signal = audio_window
        if sample_rate != FeatureEngineer.RATE:
            signal = librosa.resample(signal, orig_sr=sample_rate, target_sr=FeatureEngineer.RATE)

        features = FeatureEngineer().feature_engineer(signal)
        labels = self.model.predict(features)
        label = str(labels[0])
        is_baby = 1.0 if "Crying baby" in label else 0.0

        primary_score = is_baby
        baby_score = is_baby
        cat_score = 1.0 - is_baby

        if hasattr(self.model, "predict_proba"):
            probabilities = self.model.predict_proba(features)[0]
            classes = [str(item) for item in self.model.classes_]
            baby_candidates = [probabilities[i] for i, name in enumerate(classes) if "Crying baby" in name]
            cat_candidates = [probabilities[i] for i, name in enumerate(classes) if "cat" in name.lower()]
            if baby_candidates:
                baby_score = float(max(baby_candidates))
                primary_score = baby_score
            if cat_candidates:
                cat_score = float(max(cat_candidates))
            else:
                cat_score = max(0.0, 1.0 - baby_score)

        return DetectionResult(primary_score=primary_score, baby_score=baby_score, cat_score=cat_score)
