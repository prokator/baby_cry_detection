from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from baby_cry_detection.monitor.backends.base import DetectionBackend, DetectionResult
from baby_cry_detection.monitor.config import MonitorConfig
from baby_cry_detection.monitor.gating import GatingDecision, GatingEngine
from baby_cry_detection.monitor.notifier import TelegramNotifier


@dataclass(frozen=True)
class MonitorEvent:
    event_at: str
    primary_score: float
    baby_score: float
    cat_score: float
    clip_path: str


class MonitorService:
    def __init__(
        self,
        config: MonitorConfig,
        backend: DetectionBackend,
        notifier: TelegramNotifier,
    ) -> None:
        self.config = config
        self.backend = backend
        self.notifier = notifier
        self.gating = GatingEngine(
            baby_threshold=config.baby_threshold,
            cat_weight=config.cat_weight,
            margin_threshold=config.margin_threshold,
            cat_suppress_threshold=config.cat_suppress_threshold,
            confirm_n=config.confirm_n,
            confirm_m=config.confirm_m,
            cooldown_seconds=config.alert_cooldown_seconds,
            primary_threshold=config.primary_cry_threshold,
        )
        self.artifact_dir = Path(config.artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def should_alert(self, result: DetectionResult) -> bool:
        decision = self.evaluate_decision(result)
        return decision.ready_for_alert

    def evaluate_decision(self, result: DetectionResult) -> GatingDecision:
        return self.gating.evaluate(
            primary_score=result.primary_score,
            baby_score=result.baby_score,
            cat_score=result.cat_score,
        )

    def emit_alert(self, result: DetectionResult, clip_path: str, context: str = "") -> None:
        event = MonitorEvent(
            event_at=datetime.now().isoformat(timespec="seconds"),
            primary_score=result.primary_score,
            baby_score=result.baby_score,
            cat_score=result.cat_score,
            clip_path=str(clip_path),
        )
        self._save_event(event)
        self.notifier.send_alert(
            confidence=event.baby_score,
            cat_score=event.cat_score,
            clip_path=event.clip_path,
            context=context,
        )

    def process_scores(self, result: DetectionResult, clip_path: str, context: str = "") -> bool:
        if not self.should_alert(result):
            return False

        self.emit_alert(result=result, clip_path=clip_path, context=context)
        return True

    def _save_event(self, event: MonitorEvent) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = self.artifact_dir / f"event_{stamp}.json"
        output.write_text(json.dumps(asdict(event), indent=2), encoding="utf-8")
