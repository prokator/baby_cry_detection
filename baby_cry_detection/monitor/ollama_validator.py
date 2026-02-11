from __future__ import annotations

import json
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class ValidatorDecision:
    allow: bool
    reason: str


class OllamaValidator:
    def __init__(self, base_url: str, model: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._session = requests.Session()

    def validate(self, primary_score: float, baby_score: float, cat_score: float) -> ValidatorDecision:
        prompt = (
            "You validate baby-cry alert decisions. "
            "Input metrics:\n"
            f"primary_score={primary_score:.3f}\n"
            f"baby_score={baby_score:.3f}\n"
            f"cat_score={cat_score:.3f}\n"
            "Return strict JSON only with keys decision and reason. "
            "decision must be 'allow' or 'block'."
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        response = self._session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        outer = response.json()
        raw = outer.get("response", "{}")
        inner = json.loads(raw)
        decision = str(inner.get("decision", "block")).strip().lower()
        reason = str(inner.get("reason", "no reason"))
        return ValidatorDecision(allow=decision == "allow", reason=reason)
