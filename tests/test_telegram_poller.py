from baby_cry_detection.monitor.telegram_poller import TelegramStartPoller
from typing import Optional


class _FakeNotifier:
    def __init__(self):
        self.register_calls = []
        self.messages = []

    def register_chat_id(self, chat_id: str, accept_new_users: bool) -> bool:
        self.register_calls.append((chat_id, accept_new_users))
        return accept_new_users

    def send_direct_text(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def test_status_command_replies_with_ok():
    notifier = _FakeNotifier()
    poller = TelegramStartPoller(
        bot_token="token",
        notifier=notifier,
        accept_new_users=False,
        status_check=lambda: (True, "api=up classifier=ready"),
        test_sender=lambda _: (True, "sent"),
        enable_test_command=True,
    )

    poller._handle_update({"message": {"text": "/status", "chat": {"id": 1}}})

    assert notifier.messages
    assert "Status: OK" in notifier.messages[0][1]


def test_test_command_respects_feature_flag():
    notifier = _FakeNotifier()
    poller = TelegramStartPoller(
        bot_token="token",
        notifier=notifier,
        accept_new_users=False,
        status_check=lambda: (True, "ok"),
        test_sender=lambda _: (True, "sent"),
        enable_test_command=False,
    )

    poller._handle_update({"message": {"text": "/test", "chat": {"id": 1}}})

    assert notifier.messages
    assert "disabled" in notifier.messages[0][1].lower()


def test_cal_help_command_replies_with_clickable_commands():
    notifier = _FakeNotifier()
    poller = TelegramStartPoller(
        bot_token="token",
        notifier=notifier,
        accept_new_users=False,
        status_check=lambda: (True, "ok"),
        test_sender=lambda _: (True, "sent"),
        enable_test_command=False,
        calibration_help_text=lambda: "/cal\n/cal_start phase1 [interval_sec]\n/cal_stop",
    )

    poller._handle_update({"message": {"text": "/cal", "chat": {"id": 1}}})

    assert notifier.messages
    assert "/cal_start" in notifier.messages[0][1]
    assert "/cal_stop" in notifier.messages[0][1]


def test_cal_start_command_calls_callback_with_interval():
    notifier = _FakeNotifier()
    calls = []

    def _start(phase: str, interval: Optional[int]):
        calls.append((phase, interval))
        return True, "started"

    poller = TelegramStartPoller(
        bot_token="token",
        notifier=notifier,
        accept_new_users=False,
        status_check=lambda: (True, "ok"),
        test_sender=lambda _: (True, "sent"),
        enable_test_command=False,
        calibration_start=_start,
    )

    poller._handle_update({"message": {"text": "/cal_start phase2 20", "chat": {"id": 1}}})

    assert calls == [("phase2", 20)]
    assert notifier.messages
    assert "Calibration start: OK" in notifier.messages[0][1]


def test_cal_params_command_replies_with_payload():
    notifier = _FakeNotifier()
    poller = TelegramStartPoller(
        bot_token="token",
        notifier=notifier,
        accept_new_users=False,
        status_check=lambda: (True, "ok"),
        test_sender=lambda _: (True, "sent"),
        enable_test_command=False,
        calibration_params=lambda: (True, "phase=phase1 effective_params={}"),
    )

    poller._handle_update({"message": {"text": "/cal_params", "chat": {"id": 1}}})

    assert notifier.messages
    assert "Calibration params: OK" in notifier.messages[0][1]
