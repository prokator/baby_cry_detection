from __future__ import annotations

from collections import deque
from datetime import datetime
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Deque, Iterable

import numpy as np


MAX_MIC_GAIN_DB = 30.0


def _gain_db_from_env() -> float:
    raw = os.getenv("MIC_GAIN_DB", "0").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if value > MAX_MIC_GAIN_DB:
        return MAX_MIC_GAIN_DB
    if value < -MAX_MIC_GAIN_DB:
        return -MAX_MIC_GAIN_DB
    return value


def _apply_mic_gain(samples: np.ndarray) -> np.ndarray:
    gain_db = _gain_db_from_env()
    if abs(gain_db) < 1e-6:
        return samples
    factor = float(10 ** (gain_db / 20.0))
    boosted = np.clip(samples.astype(np.float32, copy=False) * factor, -1.0, 1.0)
    return boosted.astype(np.float32, copy=False)


class RollingAudioBuffer:
    def __init__(self, max_seconds: int, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.max_samples = max(1, int(max_seconds * sample_rate))
        self._chunks: Deque[np.ndarray] = deque()
        self._total_samples = 0

    def append(self, samples: np.ndarray) -> None:
        chunk = samples.astype(np.float32, copy=False)
        self._chunks.append(chunk)
        self._total_samples += chunk.size
        while self._total_samples > self.max_samples and self._chunks:
            dropped = self._chunks.popleft()
            self._total_samples -= dropped.size

    def snapshot(self) -> np.ndarray:
        if not self._chunks:
            return np.array([], dtype=np.float32)
        merged = np.concatenate(list(self._chunks))
        if merged.size > self.max_samples:
            merged = merged[-self.max_samples :]
        return merged


def iter_audio_windows(
    window_seconds: float,
    sample_rate: int,
    device: str = "",
) -> Iterable[np.ndarray]:
    import sounddevice as sd

    frames = max(1, int(window_seconds * sample_rate))
    while True:
        data = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device if device else None,
        )
        sd.wait()
        yield _apply_mic_gain(data[:, 0].copy())


def iter_audio_windows_resilient(
    window_seconds: float,
    sample_rate: int,
    device: str = "",
) -> Iterable[np.ndarray]:
    try:
        for window in iter_audio_windows(window_seconds=window_seconds, sample_rate=sample_rate, device=device):
            yield window
    except Exception:
        for window in _iter_windows_via_pulse(window_seconds=window_seconds, sample_rate=sample_rate, device=device):
            yield window


def _iter_windows_via_pulse(
    window_seconds: float,
    sample_rate: int,
    device: str = "",
) -> Iterable[np.ndarray]:
    import soundfile as sf

    temp_dir = Path(tempfile.gettempdir()) / "baby_cry_windows"
    temp_dir.mkdir(parents=True, exist_ok=True)
    while True:
        clip_path, _ = capture_audio_clip(
            seconds=window_seconds,
            sample_rate=sample_rate,
            output_dir=temp_dir,
            device=device,
        )
        samples, sr = sf.read(str(clip_path), dtype="float32")
        try:
            clip_path.unlink(missing_ok=True)
        except Exception:
            pass
        mono = samples[:, 0] if getattr(samples, "ndim", 1) > 1 else samples
        if sr != sample_rate:
            import librosa

            mono = librosa.resample(mono, orig_sr=sr, target_sr=sample_rate)
        yield _apply_mic_gain(np.asarray(mono, dtype=np.float32))


def capture_audio_sample(seconds: float, sample_rate: int, device: str = "") -> np.ndarray:
    import sounddevice as sd

    if device:
        selected_device = device
    else:
        input_device = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else -1
        if input_device is None or int(input_device) < 0:
            raise RuntimeError("No input microphone device is available inside container")
        selected_device = input_device

    frames = max(1, int(seconds * sample_rate))
    data = sd.rec(
        frames,
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=selected_device,
    )
    sd.wait()
    return _apply_mic_gain(data[:, 0].copy())


def probe_audio_input(device: str = "") -> tuple[bool, str]:
    try:
        import sounddevice as sd

        if device:
            sd.check_input_settings(device=device)
            return True, f"portaudio device '{device}'"

        input_device = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else -1
        if input_device is not None and int(input_device) >= 0:
            return True, f"portaudio default device {input_device}"
    except Exception as exc:
        portaudio_error = str(exc)
    else:
        portaudio_error = "no default input device"

    pulse_server = os.getenv("PULSE_SERVER", "").strip()
    if pulse_server:
        return True, f"pulse configured ({pulse_server})"
    return False, f"no input device ({portaudio_error})"


def capture_audio_clip(
    seconds: float,
    sample_rate: int,
    output_dir: str | Path,
    device: str = "",
) -> tuple[Path, str]:
    try:
        samples = capture_audio_sample(seconds=seconds, sample_rate=sample_rate, device=device)
        return save_trigger_clip(samples=samples, sample_rate=sample_rate, output_dir=output_dir), "portaudio"
    except Exception as first_error:
        pulse_server = os.getenv("PULSE_SERVER", "").strip()
        if not pulse_server:
            raise RuntimeError(
                "No input microphone device is available inside container. "
                "For Docker keep-in-container capture, configure PulseAudio bridge with PULSE_SERVER. "
                f"Original error: {first_error}"
            ) from first_error

        clip_path = _capture_with_ffmpeg_pulse(
            seconds=seconds,
            sample_rate=sample_rate,
            output_dir=output_dir,
            device=device,
        )
        return clip_path, "pulse"


def _capture_with_ffmpeg_pulse(seconds: float, sample_rate: int, output_dir: str | Path, device: str = "") -> Path:
    pulse_source = (device or os.getenv("PULSE_SOURCE", "default")).strip() or "default"
    gain_db = _gain_db_from_env()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clip_path = output / f"trigger_{stamp}.wav"

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "pulse",
        "-i",
        pulse_source,
        "-af",
        f"volume={gain_db}dB",
        "-t",
        str(seconds),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(clip_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or "unknown ffmpeg pulse error"
        raise RuntimeError(f"PulseAudio capture failed: {err}")
    return clip_path


def save_trigger_clip(samples: np.ndarray, sample_rate: int, output_dir: str | Path) -> Path:
    import soundfile as sf

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clip_path = output / f"trigger_{stamp}.wav"
    sf.write(clip_path, samples, sample_rate)
    return clip_path
