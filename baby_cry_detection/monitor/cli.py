from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path
import time

import numpy as np

from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.monitor.calibration import load_control, write_status
from baby_cry_detection.monitor.config import MonitorConfig
from baby_cry_detection.monitor.decision import passes_verifier, passes_verifier_with_thresholds
from baby_cry_detection.monitor.gpu_check import run_gpu_check
from baby_cry_detection.monitor.notifier import TelegramNotifier
from baby_cry_detection.monitor.ollama_validator import OllamaValidator
from baby_cry_detection.monitor.service import MonitorService


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Baby cry monitor")
    parser.add_argument("command", choices=["start", "status", "gpu-check"], help="Monitor command")
    parser.add_argument(
        "--clip-path",
        default="./baby_cry_detection/prediction_simulation/signal_9s.wav",
        help="Audio clip used in dry-run mode",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run a single scoring cycle")
    parser.add_argument("--max-windows", type=int, default=0, help="Stop after N windows in live mode (0=run forever)")
    return parser


def _build_backends(config: MonitorConfig):
    from baby_cry_detection.monitor.backends.existing_model import ExistingModelBackend
    from baby_cry_detection.monitor.backends.yamnet_verifier import YamnetVerifierBackend

    yamnet = YamnetVerifierBackend(
        model_handle=config.yamnet_model_handle,
        class_map_url=config.yamnet_class_map_url,
        non_cry_weight=config.non_cry_weight,
    )

    if config.backend_mode == "yamnet":
        primary = yamnet
        verifier = None
    else:
        primary = ExistingModelBackend(model_path=config.model_path)
        verifier = yamnet if config.enable_yamnet_verifier else None
    return primary, verifier


def _run_classifier_only_debug_loop(
    config: MonitorConfig,
    primary_backend,
    verifier_backend,
    max_windows: int,
    iter_audio_windows_resilient,
) -> int:
    debug_window_seconds = 5.0
    debug_interval_seconds = 15.0
    backend = verifier_backend if verifier_backend is not None else primary_backend
    backend_label = "verifier" if verifier_backend is not None else "primary"

    logging.info(
        "Classifier-only debug mode enabled (backend=%s clip=%.1fs interval=%.1fs)",
        backend_label,
        debug_window_seconds,
        debug_interval_seconds,
    )

    for idx, audio_window in enumerate(
        iter_audio_windows_resilient(
            window_seconds=debug_window_seconds,
            sample_rate=config.sample_rate,
            device=config.audio_device,
        ),
        start=1,
    ):
        loop_started = time.monotonic()
        result = backend.score(audio_window=np.asarray(audio_window, dtype=np.float32), sample_rate=config.sample_rate)
        passed = passes_verifier(config=config, result=result)

        logging.info(
            "Classifier-only debug result (pass=%s primary=%.2f baby=%.2f cat=%.2f backend=%s)",
            "yes" if passed else "no",
            result.primary_score,
            result.baby_score,
            result.cat_score,
            backend_label,
        )

        if max_windows > 0 and idx >= max_windows:
            break

        processing_seconds = time.monotonic() - loop_started
        sleep_seconds = max(0.0, debug_interval_seconds - debug_window_seconds - processing_seconds)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return 0


def main() -> int:
    from baby_cry_detection.monitor.audio import (
        RollingAudioBuffer,
        iter_audio_windows_resilient,
        save_trigger_clip,
    )

    args = _build_parser().parse_args()
    if args.command == "status":
        print("monitor_ready")
        return 0

    if args.command == "gpu-check":
        ok, detail = run_gpu_check()
        print(f"gpu_ready:{detail}" if ok else f"gpu_unavailable:{detail}")
        return 0 if ok else 1

    config = MonitorConfig.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))

    primary_backend, verifier_backend = _build_backends(config)
    notifier = TelegramNotifier(
        config.telegram_bot_token,
        config.telegram_chat_id,
        recipient_store_path=config.recipient_store_path,
    )
    service = MonitorService(config=config, backend=primary_backend, notifier=notifier)
    ollama_validator = None
    if config.enable_ollama_validator:
        ollama_validator = OllamaValidator(
            base_url=config.ollama_base_url,
            model=config.ollama_model,
            timeout_seconds=config.ollama_timeout_seconds,
        )

    if args.dry_run:
        clip_path = Path(args.clip_path)
        if not clip_path.exists():
            raise FileNotFoundError(f"Dry-run clip not found: {clip_path}")
        sample_rate = config.sample_rate
        audio_window = np.zeros(int(sample_rate * config.window_seconds), dtype=np.float32)
        result = primary_backend.score(audio_window=audio_window, sample_rate=sample_rate)
        triggered = service.process_scores(result=result, clip_path=str(clip_path), context="verifier=off")
        print("alert_sent" if triggered else "no_alert")
        return 0

    if config.debug_classifier_only_mode:
        return _run_classifier_only_debug_loop(
            config=config,
            primary_backend=primary_backend,
            verifier_backend=verifier_backend,
            max_windows=args.max_windows,
            iter_audio_windows_resilient=iter_audio_windows_resilient,
        )

    logging.info("Starting live monitor loop")
    buffer = RollingAudioBuffer(max_seconds=config.event_clip_seconds, sample_rate=config.sample_rate)
    status_next_at = 0.0

    for idx, audio_window in enumerate(
        iter_audio_windows_resilient(
            window_seconds=config.window_seconds,
            sample_rate=config.sample_rate,
            device=config.audio_device,
        ),
        start=1,
    ):
        buffer.append(audio_window)
        calibration = load_control(config.artifact_dir)

        if calibration.active and calibration.phase == "phase1":
            service.gating.update_runtime(
                primary_threshold=float(calibration.overrides.get("PRIMARY_CRY_THRESHOLD", config.primary_cry_threshold)),
                confirm_n=int(calibration.overrides.get("CONFIRM_N", config.confirm_n)),
                confirm_m=int(calibration.overrides.get("CONFIRM_M", config.confirm_m)),
                cooldown_seconds=int(
                    calibration.overrides.get("ALERT_COOLDOWN_SECONDS", config.alert_cooldown_seconds)
                ),
            )
        else:
            service.gating.update_runtime(
                primary_threshold=config.primary_cry_threshold,
                confirm_n=config.confirm_n,
                confirm_m=config.confirm_m,
                cooldown_seconds=config.alert_cooldown_seconds,
            )

        phase2_baby_threshold = float(config.baby_threshold)
        phase2_cat_threshold = float(config.cat_suppress_threshold)
        phase2_cat_weight = float(config.cat_weight)
        phase2_margin_threshold = float(config.margin_threshold)
        if calibration.active and calibration.phase == "phase2":
            phase2_baby_threshold = float(calibration.overrides.get("CRY_THRESHOLD", phase2_baby_threshold))
            phase2_cat_threshold = float(calibration.overrides.get("CAT_THRESHOLD", phase2_cat_threshold))
            phase2_cat_weight = float(calibration.overrides.get("CAT_WEIGHT", phase2_cat_weight))
            phase2_margin_threshold = float(calibration.overrides.get("MARGIN_THRESHOLD", phase2_margin_threshold))

        result = primary_backend.score(audio_window=audio_window, sample_rate=config.sample_rate)
        gate_decision = service.evaluate_decision(result)
        verifier_passed = True
        final_result = result
        verifier_context = "verifier=off"
        blocked_by = "none"

        if gate_decision.ready_for_alert:
            clip_samples = buffer.snapshot()
            if verifier_backend is not None:
                verifier_result = verifier_backend.score(audio_window=clip_samples, sample_rate=config.sample_rate)
                final_result = DetectionResult(
                    primary_score=result.primary_score,
                    baby_score=verifier_result.baby_score,
                    cat_score=verifier_result.cat_score,
                )
                verifier_passed = passes_verifier_with_thresholds(
                    result=verifier_result,
                    baby_threshold=phase2_baby_threshold,
                    cat_weight=phase2_cat_weight,
                    margin_threshold=phase2_margin_threshold,
                    cat_suppress_threshold=phase2_cat_threshold,
                )
                if not verifier_passed:
                    logging.info(
                        "[%s] Second-stage verifier suppressed alert (baby=%.2f cat=%.2f)",
                        datetime.now().strftime("%H:%M:%S"),
                        verifier_result.baby_score,
                        verifier_result.cat_score,
                    )
                    blocked_by = "verifier"

            if verifier_backend is not None and hasattr(verifier_backend, "runtime_label"):
                verifier_context = verifier_backend.runtime_label()

            if ollama_validator is not None:
                try:
                    decision = ollama_validator.validate(
                        primary_score=final_result.primary_score,
                        baby_score=final_result.baby_score,
                        cat_score=final_result.cat_score,
                    )
                except Exception as exc:
                    logging.error("Ollama validator failed, continuing without it: %s", exc)
                    decision = None

                if decision is not None and not decision.allow:
                    logging.info("Ollama validator blocked alert: %s", decision.reason)
                    blocked_by = "ollama"

            if blocked_by == "none" and calibration.active:
                logging.info(
                    "Calibration active (%s): alert suppressed (primary=%.2f baby=%.2f cat=%.2f)",
                    calibration.phase,
                    final_result.primary_score,
                    final_result.baby_score,
                    final_result.cat_score,
                )
                blocked_by = "calibration"
            elif blocked_by == "none":
                clip_path = save_trigger_clip(
                    samples=clip_samples,
                    sample_rate=config.sample_rate,
                    output_dir=config.artifact_dir,
                )
                service.emit_alert(result=final_result, clip_path=str(clip_path), context=verifier_context)
                logging.info(
                    "Alert sent (primary=%.2f baby=%.2f cat=%.2f)",
                    final_result.primary_score,
                    final_result.baby_score,
                    final_result.cat_score,
                )

        if calibration.active:
            now = time.monotonic()
            if now >= status_next_at:
                would_alert = bool(gate_decision.ready_for_alert and verifier_passed)
                payload = {
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "phase": calibration.phase,
                    "interval_seconds": calibration.interval_seconds,
                    "candidate": gate_decision.candidate,
                    "confirmed": gate_decision.confirmed,
                    "suppressed_by_cat": gate_decision.suppressed_by_cat,
                    "gate_ready": gate_decision.ready_for_alert,
                    "verifier_passed": verifier_passed,
                    "would_alert": would_alert,
                    "alert_blocked_by": blocked_by,
                    "primary_score": round(float(final_result.primary_score), 4),
                    "baby_score": round(float(final_result.baby_score), 4),
                    "cat_score": round(float(final_result.cat_score), 4),
                    "context": verifier_context,
                    "effective_params": {
                        "PRIMARY_CRY_THRESHOLD": service.gating.primary_threshold,
                        "CONFIRM_N": service.gating.confirm_n,
                        "CONFIRM_M": service.gating.confirm_m,
                        "ALERT_COOLDOWN_SECONDS": service.gating.cooldown_seconds,
                        "CRY_THRESHOLD": phase2_baby_threshold,
                        "CAT_THRESHOLD": phase2_cat_threshold,
                        "CAT_WEIGHT": phase2_cat_weight,
                        "MARGIN_THRESHOLD": phase2_margin_threshold,
                    },
                }
                write_status(config.artifact_dir, payload)
                status_next_at = now + max(2, calibration.interval_seconds)

        if args.max_windows > 0 and idx >= args.max_windows:
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
