from __future__ import annotations

import csv
from io import StringIO
from typing import Any

import requests
import numpy as np

from baby_cry_detection.monitor.backends.base import DetectionResult


class YamnetVerifierBackend:
    """YAMNet second-stage verifier backend (lazy loaded)."""

    def __init__(
        self,
        model_handle: str = "https://tfhub.dev/google/yamnet/1",
        class_map_url: str = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv",
        non_cry_weight: float = 1.0,
    ) -> None:
        self.model_handle = model_handle
        self.class_map_url = class_map_url
        self.non_cry_weight = max(0.0, float(non_cry_weight))
        self._yamnet_model = None
        self._class_names: list[str] = []
        self._loaded = False
        self._last_used_fallback = False
        self._last_gpu_visible = False

    @staticmethod
    def _aggregate_scores(mean_scores: np.ndarray, class_names: list[str], non_cry_weight: float) -> DetectionResult:
        lowered = [name.lower() for name in class_names]
        baby_idx = [i for i, name in enumerate(lowered) if "baby cry" in name or "infant cry" in name]
        cat_idx = [i for i, name in enumerate(lowered) if "cat" in name or "meow" in name]

        baby_score = float(max([mean_scores[i] for i in baby_idx], default=0.0))
        cat_score = float(max([mean_scores[i] for i in cat_idx], default=0.0))

        excluded = set(baby_idx + cat_idx)
        non_target_scores = [mean_scores[i] for i in range(mean_scores.shape[0]) if i not in excluded]
        non_target_score = float(max(non_target_scores, default=0.0))

        suppressor = max(cat_score, min(1.0, non_cry_weight * non_target_score))
        adjusted_baby = max(0.0, min(1.0, baby_score - max(0.0, suppressor - cat_score)))
        return DetectionResult(primary_score=adjusted_baby, baby_score=adjusted_baby, cat_score=suppressor)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        import tensorflow_hub as hub

        self._yamnet_model = hub.load(self.model_handle)
        response = requests.get(self.class_map_url, timeout=20)
        response.raise_for_status()
        rows = csv.DictReader(StringIO(response.text))
        self._class_names = [str(row.get("display_name", "")).strip() for row in rows]
        self._loaded = True

    def score(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        if audio_window.size == 0:
            return DetectionResult(primary_score=0.0, baby_score=0.0, cat_score=0.0)
        try:
            self._ensure_loaded()
            result = self._score_with_yamnet(audio_window=audio_window, sample_rate=sample_rate)
            self._last_used_fallback = False
            return result
        except Exception:
            self._last_used_fallback = True
            return self._score_fallback(audio_window=audio_window, sample_rate=sample_rate)

    def _score_with_yamnet(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        import librosa
        import tensorflow as tf

        self._last_gpu_visible = len(tf.config.list_physical_devices("GPU")) > 0

        waveform = np.asarray(audio_window, dtype=np.float32)
        if sample_rate != 16000:
            waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=16000)
        waveform = np.clip(waveform, -1.0, 1.0).astype(np.float32)
        model = self._yamnet_model
        if model is None:
            raise RuntimeError("YAMNet model is not loaded")

        scores, _, _ = model(tf.convert_to_tensor(waveform))
        mean_scores = np.mean(np.asarray(scores), axis=0)
        return self._aggregate_scores(mean_scores=mean_scores, class_names=self._class_names, non_cry_weight=self.non_cry_weight)

    def runtime_label(self) -> str:
        if self._last_used_fallback:
            return "yamnet=fallback device=cpu"
        if self._loaded:
            return "yamnet=active device=gpu" if self._last_gpu_visible else "yamnet=active device=cpu"
        return "yamnet=not_loaded device=unknown"

    def _score_fallback(self, audio_window: np.ndarray, sample_rate: int) -> DetectionResult:
        import librosa

        rms = float(np.sqrt(np.mean(np.square(audio_window))))
        zcr = float(np.mean(np.abs(np.diff(np.sign(audio_window))) > 0))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=audio_window, sr=sample_rate)))

        baby_energy = min(1.0, max(0.0, 3.0 * rms))
        baby_pitch_factor = 1.0 - min(1.0, centroid / 4000.0)
        baby_score = min(1.0, max(0.0, 0.75 * baby_energy + 0.25 * baby_pitch_factor))

        cat_pitch_factor = min(1.0, centroid / 2500.0)
        cat_score = min(1.0, max(0.0, 0.55 * cat_pitch_factor + 0.45 * zcr))
        suppressor = max(cat_score, min(1.0, self.non_cry_weight * (1.0 - baby_score)))
        adjusted_baby = max(0.0, min(1.0, baby_score - max(0.0, suppressor - cat_score)))
        return DetectionResult(primary_score=adjusted_baby, baby_score=adjusted_baby, cat_score=suppressor)
