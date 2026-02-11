import pytest

from baby_cry_detection.monitor.config import MonitorConfig


def test_config_from_env_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("BACKEND_MODE", "existing_model")
    monkeypatch.setenv("BABY_THRESHOLD", "0.5")
    monkeypatch.setenv("DEBUG_CLASSIFIER_ONLY_MODE", "true")

    config = MonitorConfig.from_env()

    assert config.telegram_bot_token == "token"
    assert config.telegram_chat_id == "chat"
    assert config.baby_threshold == 0.5
    assert config.debug_classifier_only_mode is True


def test_config_requires_telegram_settings(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValueError):
        MonitorConfig.from_env()


def test_invalid_backend_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("BACKEND_MODE", "invalid")

    with pytest.raises(ValueError):
        MonitorConfig.from_env()
