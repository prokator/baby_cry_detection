from __future__ import annotations

import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MonitorConfig:
    telegram_bot_token: str
    telegram_chat_id: str = ""
    accept_new_users: bool = False
    recipient_store_path: str = "/app/artifacts/telegram_recipients.json"
    enable_telegram_poller: bool = True
    enable_manual_registration: bool = False
    enable_telegram_test_command: bool = False
    telegram_test_seconds: int = 3
    backend_mode: str = "existing_model"
    enable_yamnet_verifier: bool = True
    enable_ollama_validator: bool = False
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: int = 10
    sample_rate: int = 16000
    audio_device: str = ""
    mic_gain_db: float = 0.0
    primary_cry_threshold: float = 0.5
    baby_threshold: float = 0.45
    cat_weight: float = 1.0
    non_cry_weight: float = 1.0
    margin_threshold: float = 0.15
    cat_suppress_threshold: float = 0.45
    confirm_n: int = 3
    confirm_m: int = 5
    alert_cooldown_seconds: int = 60
    window_seconds: float = 0.96
    event_clip_seconds: int = 8
    debug_classifier_only_mode: bool = False
    log_level: str = "INFO"
    artifact_dir: str = "/app/artifacts"
    model_path: str = ""
    yamnet_model_handle: str = "https://tfhub.dev/google/yamnet/1"
    yamnet_class_map_url: str = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        backend_mode = os.getenv("BACKEND_MODE", "existing_model").strip().lower()
        if backend_mode not in {"existing_model", "yamnet"}:
            raise ValueError("BACKEND_MODE must be 'existing_model' or 'yamnet'")

        cry_threshold = _float_env("CRY_THRESHOLD", _float_env("BABY_THRESHOLD", 0.45))
        cat_threshold = _float_env("CAT_THRESHOLD", _float_env("CAT_SUPPRESS_THRESHOLD", 0.45))

        return cls(
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            accept_new_users=_bool_env("ACCEPT_NEW_USERS", False),
            recipient_store_path=os.getenv("RECIPIENT_STORE_PATH", "/app/artifacts/telegram_recipients.json").strip(),
            enable_telegram_poller=_bool_env("ENABLE_TELEGRAM_POLLER", True),
            enable_manual_registration=_bool_env("ENABLE_MANUAL_REGISTRATION", False),
            enable_telegram_test_command=_bool_env("ENABLE_TELEGRAM_TEST_COMMAND", False),
            telegram_test_seconds=_int_env("TELEGRAM_TEST_SECONDS", 3),
            backend_mode=backend_mode,
            enable_yamnet_verifier=_bool_env("ENABLE_YAMNET_VERIFIER", True),
            enable_ollama_validator=_bool_env("ENABLE_OLLAMA_VALIDATOR", False),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").strip(),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2").strip(),
            ollama_timeout_seconds=_int_env("OLLAMA_TIMEOUT_SECONDS", 10),
            sample_rate=_int_env("SAMPLE_RATE", 16000),
            audio_device=os.getenv("AUDIO_DEVICE", "").strip(),
            mic_gain_db=_float_env("MIC_GAIN_DB", 0.0),
            primary_cry_threshold=_float_env("PRIMARY_CRY_THRESHOLD", 0.5),
            baby_threshold=cry_threshold,
            cat_weight=_float_env("CAT_WEIGHT", 1.0),
            non_cry_weight=_float_env("NON_CRY_WEIGHT", 1.0),
            margin_threshold=_float_env("MARGIN_THRESHOLD", 0.15),
            cat_suppress_threshold=cat_threshold,
            confirm_n=_int_env("CONFIRM_N", 3),
            confirm_m=_int_env("CONFIRM_M", 5),
            alert_cooldown_seconds=_int_env("ALERT_COOLDOWN_SECONDS", 60),
            window_seconds=_float_env("WINDOW_SECONDS", 0.96),
            event_clip_seconds=_int_env("EVENT_CLIP_SECONDS", 8),
            debug_classifier_only_mode=_bool_env("DEBUG_CLASSIFIER_ONLY_MODE", False),
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            artifact_dir=os.getenv("ARTIFACT_DIR", "/app/artifacts").strip(),
            model_path=os.getenv("MODEL_PATH", "").strip(),
            yamnet_model_handle=os.getenv("YAMNET_MODEL_HANDLE", "https://tfhub.dev/google/yamnet/1").strip(),
            yamnet_class_map_url=os.getenv(
                "YAMNET_CLASS_MAP_URL",
                "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv",
            ).strip(),
        )
