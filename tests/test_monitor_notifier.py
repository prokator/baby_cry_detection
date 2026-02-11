from datetime import datetime
from typing import Any

from baby_cry_detection.monitor.notifier import TelegramNotifier


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, files=None, timeout=None):
        self.calls.append({"url": url, "data": data, "files": files, "timeout": timeout})
        return _FakeResponse()


def test_build_message_format():
    dt = datetime(2026, 2, 10, 22, 14, 5)
    text = TelegramNotifier.build_message(confidence=0.87, cat_score=0.12, event_at=dt)
    assert "[Baby Monitor]" in text
    assert "confidence=0.87" in text
    assert "cat_score=0.12" in text


def test_send_alert_posts_text_and_clip(tmp_path):
    clip = tmp_path / "trigger.mp3"
    clip.write_bytes(b"ID3")

    notifier = TelegramNotifier(
        bot_token="token",
        chat_id="chat",
        recipient_store_path=str(tmp_path / "recipients.json"),
    )
    fake = _FakeSession()
    # test double for network calls
    notifier._session = fake  # type: ignore[assignment]

    result = notifier.send_alert(confidence=0.8, cat_score=0.1, clip_path=clip)

    assert result["text_sent"]
    assert result["clip_sent"]
    assert len(fake.calls) == 2
    assert fake.calls[0]["url"].endswith("/sendMessage")
    assert fake.calls[1]["url"].endswith("/sendAudio")


def test_register_chat_id_respects_policy(tmp_path):
    notifier = TelegramNotifier(
        bot_token="token",
        chat_id="",
        recipient_store_path=str(tmp_path / "recipients.json"),
    )

    assert not notifier.register_chat_id("123", accept_new_users=False)
    assert notifier.register_chat_id("123", accept_new_users=True)
