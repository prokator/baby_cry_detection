from __future__ import annotations

import json
from pathlib import Path


class TelegramRecipientStore:
    def __init__(self, file_path: str) -> None:
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_chat_ids(self) -> list[str]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if str(item).strip()]

    def add_chat_id(self, chat_id: str) -> None:
        chat_id = str(chat_id).strip()
        if not chat_id:
            return
        current = set(self.list_chat_ids())
        current.add(chat_id)
        self.path.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")
