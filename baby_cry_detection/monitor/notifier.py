from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
from typing import Any

import requests

from baby_cry_detection.monitor.recipient_store import TelegramRecipientStore


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        recipient_store_path: str,
        timeout_seconds: int = 15,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._session = requests.Session()
        self._store = TelegramRecipientStore(recipient_store_path)

    @staticmethod
    def build_message(
        confidence: float,
        cat_score: float,
        event_at: datetime | None = None,
        context: str = "",
    ) -> str:
        event_time = (event_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
        message = (
            "[Baby Monitor] Cry detected at "
            f"{event_time} (confidence={confidence:.2f}, cat_score={cat_score:.2f})"
        )
        if context:
            message = f"{message} [{context}]"
        return message

    def _recipients(self) -> list[str]:
        recipients = set(self._store.list_chat_ids())
        if self.chat_id:
            recipients.add(self.chat_id)
        return sorted(recipients)

    def send_direct_text(self, chat_id: str, message: str) -> None:
        response = self._session.post(
            f"{self.base_url}/sendMessage",
            data={"chat_id": chat_id, "text": message},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def send_direct_clip(self, chat_id: str, clip_path: str | Path, caption: str) -> None:
        path = Path(clip_path)
        if not path.exists():
            raise FileNotFoundError(f"Clip not found: {path}")

        path = self._prepare_clip_for_telegram(path)

        with path.open("rb") as fh:
            response = self._session.post(
                f"{self.base_url}/sendAudio",
                data={"chat_id": chat_id, "caption": caption},
                files={"audio": (path.name, fh, "audio/mpeg")},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()

    def _prepare_clip_for_telegram(self, source_path: Path) -> Path:
        if source_path.suffix.lower() == ".mp3":
            return source_path

        target = source_path.with_suffix(".mp3")
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(target),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not target.exists():
            err = result.stderr.strip() or result.stdout.strip() or "unknown ffmpeg error"
            raise RuntimeError(f"Failed converting audio to mp3: {err}")
        return target

    def send_text(self, message: str) -> None:
        recipients = self._recipients()
        if not recipients:
            raise ValueError("No Telegram recipients configured")

        for chat_id in recipients:
            self.send_direct_text(chat_id=chat_id, message=message)

    def send_clip(self, clip_path: str | Path, caption: str) -> None:
        recipients = self._recipients()
        if not recipients:
            raise ValueError("No Telegram recipients configured")

        path = Path(clip_path)
        if not path.exists():
            raise FileNotFoundError(f"Clip not found: {path}")

        for chat_id in recipients:
            self.send_direct_clip(chat_id=chat_id, clip_path=path, caption=caption)

    def register_chat_id(self, chat_id: str, accept_new_users: bool) -> bool:
        if not accept_new_users:
            return False
        self._store.add_chat_id(chat_id)
        return True

    def send_alert(self, confidence: float, cat_score: float, clip_path: str | Path, context: str = "") -> dict[str, Any]:
        message = self.build_message(confidence=confidence, cat_score=cat_score, context=context)
        self.send_text(message)

        try:
            self.send_clip(clip_path=clip_path, caption="Triggering audio clip")
            return {"text_sent": True, "clip_sent": True}
        except Exception:
            self.send_clip(clip_path=clip_path, caption="Triggering audio clip (retry)")
            return {"text_sent": True, "clip_sent": True, "retried": True}
