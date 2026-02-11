from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import requests

from baby_cry_detection.monitor.notifier import TelegramNotifier


class TelegramStartPoller:
    def __init__(
        self,
        bot_token: str,
        notifier: TelegramNotifier,
        accept_new_users: bool,
        status_check: Callable[[], tuple[bool, str]],
        test_sender: Callable[[str], tuple[bool, str]],
        enable_test_command: bool,
        calibration_help_text: Callable[[], str] | None = None,
        calibration_start: Callable[[str, int | None], tuple[bool, str]] | None = None,
        calibration_set: Callable[[str, str], tuple[bool, str]] | None = None,
        calibration_params: Callable[[], tuple[bool, str]] | None = None,
        calibration_status: Callable[[], tuple[bool, str]] | None = None,
        calibration_stop: Callable[[], tuple[bool, str]] | None = None,
        calibration_watch_interval: Callable[[], int] | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.notifier = notifier
        self.accept_new_users = accept_new_users
        self.status_check = status_check
        self.test_sender = test_sender
        self.enable_test_command = enable_test_command
        self.calibration_help_text = calibration_help_text
        self.calibration_start = calibration_start
        self.calibration_set = calibration_set
        self.calibration_params = calibration_params
        self.calibration_status = calibration_status
        self.calibration_stop = calibration_stop
        self.calibration_watch_interval = calibration_watch_interval
        self._offset = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._watch_thread: threading.Thread | None = None
        self._watchers: dict[str, dict[str, float]] = {}

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._watch_thread = threading.Thread(target=self._run_watch, daemon=True)
        self._thread.start()
        self._watch_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=5)

    def _run(self) -> None:
        session = requests.Session()
        base_url = f"https://api.telegram.org/bot{self.bot_token}"
        while not self._stop.is_set():
            try:
                response = session.get(
                    f"{base_url}/getUpdates",
                    params={"timeout": 25, "offset": self._offset},
                    timeout=35,
                )
                response.raise_for_status()
                payload = response.json()
                for update in payload.get("result", []):
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    self._handle_update(update)
            except Exception as exc:
                logging.error("Telegram poller error: %s", exc)
                time.sleep(2)

    def _run_watch(self) -> None:
        while not self._stop.is_set():
            if not self._watchers:
                time.sleep(0.5)
                continue

            now = time.monotonic()
            for chat_id, watch in list(self._watchers.items()):
                if now < watch.get("next_at", 0.0):
                    continue

                if self.calibration_status is None:
                    self._safe_reply(chat_id, "Calibration status command is unavailable.")
                    self._watchers.pop(chat_id, None)
                    continue

                ok, detail = self.calibration_status()
                prefix = "Calibration: OK" if ok else "Calibration: ERROR"
                self._safe_reply(chat_id, f"{prefix}. {detail}")
                interval = max(2.0, float(watch.get("interval", 15.0)))
                watch["next_at"] = now + interval
                if not ok:
                    self._watchers.pop(chat_id, None)

            time.sleep(0.5)

    def _handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        text = str(message.get("text", "")).strip()
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", "")).strip()
        if not chat_id or not text:
            return

        command = text.split()[0].strip().lower()
        if command == "/start":
            self._handle_start(chat_id)
            return
        if command == "/status":
            self._handle_status(chat_id)
            return
        if command == "/test":
            self._handle_test(chat_id)
            return
        if command == "/cal":
            self._handle_cal_help(chat_id)
            return
        if command == "/cal_start":
            self._handle_cal_start(chat_id, text)
            return
        if command == "/cal_set":
            self._handle_cal_set(chat_id, text)
            return
        if command == "/cal_params":
            self._handle_cal_params(chat_id)
            return
        if command == "/cal_status":
            self._handle_cal_status(chat_id)
            return
        if command == "/cal_watch":
            self._handle_cal_watch(chat_id, text)
            return
        if command == "/cal_watch_stop":
            self._handle_cal_watch_stop(chat_id)
            return
        if command == "/cal_stop":
            self._handle_cal_stop(chat_id)

    def _handle_start(self, chat_id: str) -> None:
        added = self.notifier.register_chat_id(chat_id=chat_id, accept_new_users=self.accept_new_users)
        if added:
            logging.info("Registered Telegram chat_id from poller")
            self._safe_reply(chat_id, "Registration successful. You will receive baby-cry alerts.")
            return
        self._safe_reply(chat_id, "Registration is currently closed.")

    def _handle_status(self, chat_id: str) -> None:
        ok, detail = self.status_check()
        prefix = "Status: OK" if ok else "Status: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_test(self, chat_id: str) -> None:
        if not self.enable_test_command:
            self._safe_reply(chat_id, "Test command is disabled.")
            return

        ok, detail = self.test_sender(chat_id)
        prefix = "Test: OK" if ok else "Test: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_cal_help(self, chat_id: str) -> None:
        if self.calibration_help_text is None:
            self._safe_reply(chat_id, "Calibration commands are unavailable.")
            return
        self._safe_reply(chat_id, self.calibration_help_text())

    def _handle_cal_start(self, chat_id: str, text: str) -> None:
        if self.calibration_start is None:
            self._safe_reply(chat_id, "Calibration start is unavailable.")
            return

        parts = text.split()
        if len(parts) < 2:
            self._safe_reply(chat_id, "Usage: /cal_start phase1|phase2 [interval_sec]")
            return

        phase = parts[1].strip().lower()
        interval: int | None = None
        if len(parts) >= 3:
            try:
                interval = int(parts[2])
            except ValueError:
                self._safe_reply(chat_id, "Interval must be an integer number of seconds.")
                return

        ok, detail = self.calibration_start(phase, interval)
        prefix = "Calibration start: OK" if ok else "Calibration start: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_cal_set(self, chat_id: str, text: str) -> None:
        if self.calibration_set is None:
            self._safe_reply(chat_id, "Calibration parameter updates are unavailable.")
            return

        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            self._safe_reply(chat_id, "Usage: /cal_set <param> <value>")
            return

        ok, detail = self.calibration_set(parts[1], parts[2])
        prefix = "Calibration set: OK" if ok else "Calibration set: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_cal_status(self, chat_id: str) -> None:
        if self.calibration_status is None:
            self._safe_reply(chat_id, "Calibration status is unavailable.")
            return
        ok, detail = self.calibration_status()
        prefix = "Calibration: OK" if ok else "Calibration: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_cal_params(self, chat_id: str) -> None:
        if self.calibration_params is None:
            self._safe_reply(chat_id, "Calibration params are unavailable.")
            return
        ok, detail = self.calibration_params()
        prefix = "Calibration params: OK" if ok else "Calibration params: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")

    def _handle_cal_watch(self, chat_id: str, text: str) -> None:
        parts = text.split()
        interval: float | None = None
        if len(parts) >= 2:
            try:
                interval = float(parts[1])
            except ValueError:
                self._safe_reply(chat_id, "Usage: /cal_watch [interval_sec]")
                return

        if interval is None:
            interval = float(self.calibration_watch_interval() if self.calibration_watch_interval else 15)
        interval = max(2.0, min(interval, 600.0))

        self._watchers[chat_id] = {
            "interval": interval,
            "next_at": time.monotonic(),
        }
        self._safe_reply(chat_id, f"Calibration watch enabled every {int(interval)}s. Use /cal_watch_stop to stop.")

    def _handle_cal_watch_stop(self, chat_id: str) -> None:
        existed = chat_id in self._watchers
        self._watchers.pop(chat_id, None)
        if existed:
            self._safe_reply(chat_id, "Calibration watch stopped.")
        else:
            self._safe_reply(chat_id, "Calibration watch is not active for this chat.")

    def _handle_cal_stop(self, chat_id: str) -> None:
        if self.calibration_stop is None:
            self._safe_reply(chat_id, "Calibration stop is unavailable.")
            return

        ok, detail = self.calibration_stop()
        prefix = "Calibration stop: OK" if ok else "Calibration stop: ERROR"
        self._safe_reply(chat_id, f"{prefix}. {detail}")
        if ok:
            self._watchers.clear()

    def _safe_reply(self, chat_id: str, text: str) -> None:
        try:
            self.notifier.send_direct_text(chat_id, text)
        except Exception:
            pass
