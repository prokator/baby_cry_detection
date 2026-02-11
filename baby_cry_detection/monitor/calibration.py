from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CALIBRATION_INTERVAL_SECONDS = 15

PHASE_PARAMETER_SPECS: dict[str, dict[str, type]] = {
    "phase1": {
        "PRIMARY_CRY_THRESHOLD": float,
        "CONFIRM_N": int,
        "CONFIRM_M": int,
        "ALERT_COOLDOWN_SECONDS": int,
    },
    "phase2": {
        "CRY_THRESHOLD": float,
        "CAT_THRESHOLD": float,
        "CAT_WEIGHT": float,
        "MARGIN_THRESHOLD": float,
    },
}


@dataclass(frozen=True)
class CalibrationControl:
    active: bool
    phase: str
    interval_seconds: int
    overrides: dict[str, float | int]


def control_file_path(artifact_dir: str | Path) -> Path:
    return Path(artifact_dir) / "calibration_control.json"


def status_file_path(artifact_dir: str | Path) -> Path:
    return Path(artifact_dir) / "calibration_status.json"


def default_control() -> CalibrationControl:
    return CalibrationControl(
        active=False,
        phase="phase1",
        interval_seconds=DEFAULT_CALIBRATION_INTERVAL_SECONDS,
        overrides={},
    )


def load_control(artifact_dir: str | Path) -> CalibrationControl:
    path = control_file_path(artifact_dir)
    if not path.exists():
        return default_control()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_control()

    phase = str(payload.get("phase", "phase1")).strip().lower()
    if phase not in PHASE_PARAMETER_SPECS:
        phase = "phase1"

    interval = _to_interval(payload.get("interval_seconds"), DEFAULT_CALIBRATION_INTERVAL_SECONDS)
    overrides = _normalize_overrides(phase=phase, raw=payload.get("overrides"))
    active = bool(payload.get("active", False))
    return CalibrationControl(active=active, phase=phase, interval_seconds=interval, overrides=overrides)


def save_control(artifact_dir: str | Path, control: CalibrationControl) -> None:
    path = control_file_path(artifact_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": control.active,
        "phase": control.phase,
        "interval_seconds": control.interval_seconds,
        "overrides": control.overrides,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def start_calibration(artifact_dir: str | Path, phase: str, interval_seconds: int | None = None) -> CalibrationControl:
    normalized_phase = phase.strip().lower()
    if normalized_phase not in PHASE_PARAMETER_SPECS:
        raise ValueError("phase must be phase1 or phase2")
    interval = _to_interval(interval_seconds, DEFAULT_CALIBRATION_INTERVAL_SECONDS)
    control = CalibrationControl(active=True, phase=normalized_phase, interval_seconds=interval, overrides={})
    save_control(artifact_dir, control)
    return control


def stop_calibration(artifact_dir: str | Path) -> tuple[CalibrationControl, CalibrationControl]:
    previous = load_control(artifact_dir)
    current = CalibrationControl(
        active=False,
        phase=previous.phase,
        interval_seconds=previous.interval_seconds,
        overrides={},
    )
    save_control(artifact_dir, current)
    return previous, current


def set_calibration_interval(artifact_dir: str | Path, interval_seconds: int) -> CalibrationControl:
    current = load_control(artifact_dir)
    updated = CalibrationControl(
        active=current.active,
        phase=current.phase,
        interval_seconds=_to_interval(interval_seconds, DEFAULT_CALIBRATION_INTERVAL_SECONDS),
        overrides=current.overrides,
    )
    save_control(artifact_dir, updated)
    return updated


def set_override(artifact_dir: str | Path, parameter: str, raw_value: str) -> tuple[CalibrationControl, str, float | int]:
    current = load_control(artifact_dir)
    if not current.active:
        raise ValueError("calibration is not active")

    key = parameter.strip().upper()
    spec = PHASE_PARAMETER_SPECS.get(current.phase, {})
    expected_type = spec.get(key)
    if expected_type is None:
        allowed = ", ".join(sorted(spec.keys()))
        raise ValueError(f"parameter not allowed for {current.phase}. allowed: {allowed}")

    value = _parse_typed_value(raw_value, expected_type)
    overrides = dict(current.overrides)
    overrides[key] = value
    updated = CalibrationControl(
        active=current.active,
        phase=current.phase,
        interval_seconds=current.interval_seconds,
        overrides=overrides,
    )
    save_control(artifact_dir, updated)
    return updated, key, value


def build_calibration_help_text() -> str:
    return "\n".join(
        [
            "Calibration commands:",
            "/cal",
            "/cal_start phase1 [interval_sec]",
            "/cal_start phase2 [interval_sec]",
            "/cal_set <param> <value>",
            "/cal_params",
            "/cal_status",
            "/cal_watch [interval_sec]",
            "/cal_watch_stop",
            "/cal_stop",
            "",
            "phase1 params: PRIMARY_CRY_THRESHOLD, CONFIRM_N, CONFIRM_M, ALERT_COOLDOWN_SECONDS",
            "phase2 params: CRY_THRESHOLD, CAT_THRESHOLD, CAT_WEIGHT, MARGIN_THRESHOLD",
            f"default interval: {DEFAULT_CALIBRATION_INTERVAL_SECONDS}s",
        ]
    )


def build_stop_summary(previous: CalibrationControl) -> str:
    lines = [
        f"Calibration stopped for {previous.phase}. Alerts re-enabled and .env defaults restored.",
        "Final command state:",
        f"/cal_start {previous.phase} {previous.interval_seconds}",
    ]
    for key in sorted(previous.overrides):
        lines.append(f"/cal_set {key} {previous.overrides[key]}")
    if not previous.overrides:
        lines.append("(no parameter overrides were applied)")
    return "\n".join(lines)


def write_status(artifact_dir: str | Path, payload: dict[str, Any]) -> None:
    path = status_file_path(artifact_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_status(artifact_dir: str | Path) -> dict[str, Any]:
    path = status_file_path(artifact_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _to_interval(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return default
    return max(2, min(interval, 600))


def _parse_typed_value(raw_value: str, expected_type: type) -> float | int:
    text = str(raw_value).strip()
    if expected_type is int:
        value = int(text)
        if value < 0:
            raise ValueError("integer value must be >= 0")
        return value
    value = float(text)
    return value


def _normalize_overrides(phase: str, raw: Any) -> dict[str, float | int]:
    if not isinstance(raw, dict):
        return {}

    specs = PHASE_PARAMETER_SPECS.get(phase, {})
    normalized: dict[str, float | int] = {}
    for key, value in raw.items():
        lookup = str(key).strip().upper()
        expected = specs.get(lookup)
        if expected is None:
            continue
        try:
            normalized[lookup] = _parse_typed_value(str(value), expected)
        except Exception:
            continue
    return normalized
