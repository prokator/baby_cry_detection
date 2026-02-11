from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque


@dataclass(frozen=True)
class GatingDecision:
    candidate: bool
    confirmed: bool
    suppressed_by_cat: bool
    ready_for_alert: bool


class GatingEngine:
    def __init__(
        self,
        baby_threshold: float,
        cat_weight: float,
        margin_threshold: float,
        cat_suppress_threshold: float,
        confirm_n: int,
        confirm_m: int,
        cooldown_seconds: int,
        primary_threshold: float = 0.5,
    ) -> None:
        self.primary_threshold = primary_threshold
        self.baby_threshold = baby_threshold
        self.cat_weight = cat_weight
        self.margin_threshold = margin_threshold
        self.cat_suppress_threshold = cat_suppress_threshold
        self.confirm_n = confirm_n
        self.confirm_m = confirm_m
        self.cooldown_seconds = cooldown_seconds
        self._history: Deque[bool] = deque(maxlen=confirm_m)
        self._last_alert_at: datetime | None = None

    def evaluate(self, primary_score: float, baby_score: float, cat_score: float) -> GatingDecision:
        candidate = (
            primary_score >= self.primary_threshold
            and baby_score >= self.baby_threshold
            and (baby_score - self.cat_weight * cat_score) >= self.margin_threshold
        )
        suppressed_by_cat = cat_score >= self.cat_suppress_threshold and not (
            baby_score > cat_score and baby_score >= self.baby_threshold
        )

        self._history.append(candidate and not suppressed_by_cat)
        confirmed = sum(self._history) >= self.confirm_n

        now = datetime.utcnow()
        cooldown_ready = self._last_alert_at is None or (
            now - self._last_alert_at >= timedelta(seconds=self.cooldown_seconds)
        )
        ready_for_alert = confirmed and not suppressed_by_cat and cooldown_ready

        if ready_for_alert:
            self._last_alert_at = now

        return GatingDecision(
            candidate=candidate,
            confirmed=confirmed,
            suppressed_by_cat=suppressed_by_cat,
            ready_for_alert=ready_for_alert,
        )

    def update_runtime(
        self,
        *,
        primary_threshold: float | None = None,
        confirm_n: int | None = None,
        confirm_m: int | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        if primary_threshold is not None:
            self.primary_threshold = float(primary_threshold)
        if confirm_n is not None:
            self.confirm_n = max(1, int(confirm_n))
        if confirm_m is not None:
            new_confirm_m = max(1, int(confirm_m))
            if new_confirm_m != self.confirm_m:
                history_tail = list(self._history)[-new_confirm_m:]
                self._history = deque(history_tail, maxlen=new_confirm_m)
                self.confirm_m = new_confirm_m
        if cooldown_seconds is not None:
            self.cooldown_seconds = max(0, int(cooldown_seconds))
