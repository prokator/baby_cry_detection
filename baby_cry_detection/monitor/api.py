from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from baby_cry_detection.monitor.audio import capture_audio_clip, probe_audio_input
from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.monitor.calibration import (
    DEFAULT_CALIBRATION_INTERVAL_SECONDS,
    PHASE_PARAMETER_SPECS,
    build_calibration_help_text,
    build_stop_summary,
    load_control,
    read_status,
    set_override,
    start_calibration,
    stop_calibration,
)
from baby_cry_detection.monitor.config import MonitorConfig
from baby_cry_detection.monitor.decision import passes_verifier
from baby_cry_detection.monitor.gpu_check import run_gpu_check
from baby_cry_detection.monitor.notifier import TelegramNotifier
from baby_cry_detection.monitor.telegram_poller import TelegramStartPoller


def create_app() -> FastAPI:
    app = FastAPI(title="Cat vs Child Classifier", version="0.1.0")

    from baby_cry_detection.monitor.backends.existing_model import ExistingModelBackend
    from baby_cry_detection.monitor.backends.yamnet_verifier import YamnetVerifierBackend

    config = MonitorConfig.from_env()
    primary_backend = ExistingModelBackend(model_path=config.model_path)
    verifier_backend = YamnetVerifierBackend() if config.enable_yamnet_verifier else None
    notifier = TelegramNotifier(
        config.telegram_bot_token,
        config.telegram_chat_id,
        recipient_store_path=config.recipient_store_path,
    )

    def _calibration_start(phase: str, interval_seconds: int | None) -> tuple[bool, str]:
        try:
            control = start_calibration(config.artifact_dir, phase=phase, interval_seconds=interval_seconds)
            allowed = ", ".join(sorted(PHASE_PARAMETER_SPECS.get(control.phase, {}).keys()))
            return (
                True,
                f"active phase={control.phase} interval={control.interval_seconds}s alerts=disabled allowed_params={allowed}",
            )
        except Exception as exc:
            return False, str(exc)

    def _calibration_set(parameter: str, value: str) -> tuple[bool, str]:
        try:
            control, key, parsed = set_override(config.artifact_dir, parameter=parameter, raw_value=value)
            return True, f"phase={control.phase} set {key}={parsed}"
        except Exception as exc:
            return False, str(exc)

    def _format_calibration_status() -> tuple[bool, str]:
        control = load_control(config.artifact_dir)
        status = read_status(config.artifact_dir)
        if not control.active:
            return False, "calibration inactive. Use /cal_start phase1|phase2 [interval_sec]."

        if not status:
            return True, f"phase={control.phase} active interval={control.interval_seconds}s waiting_for_live_status"

        updated_at = status.get("updated_at", "unknown")
        primary = float(status.get("primary_score", 0.0))
        baby = float(status.get("baby_score", 0.0))
        cat = float(status.get("cat_score", 0.0))
        candidate = bool(status.get("candidate", False))
        confirmed = bool(status.get("confirmed", False))
        suppressed = bool(status.get("suppressed_by_cat", False))
        verifier_passed = bool(status.get("verifier_passed", False))
        would_alert = bool(status.get("would_alert", False))
        blocked = str(status.get("alert_blocked_by", "none"))
        context = str(status.get("context", ""))
        params = status.get("effective_params", {})
        return (
            True,
            f"phase={control.phase} interval={control.interval_seconds}s updated={updated_at} "
            f"primary={primary:.2f} baby={baby:.2f} cat={cat:.2f} "
            f"candidate={candidate} confirmed={confirmed} suppressed={suppressed} verifier_passed={verifier_passed} "
            f"would_alert={would_alert} alert_blocked_by={blocked} context={context} params={params}",
        )

    def _format_calibration_params() -> tuple[bool, str]:
        control = load_control(config.artifact_dir)
        if not control.active:
            return False, "calibration inactive. Use /cal_start phase1|phase2 [interval_sec]."

        status = read_status(config.artifact_dir)
        effective = status.get("effective_params") if isinstance(status, dict) else None
        if not isinstance(effective, dict) or not effective:
            effective = dict(control.overrides)

        return (
            True,
            f"phase={control.phase} interval={control.interval_seconds}s overrides={control.overrides} effective_params={effective}",
        )

    def _calibration_stop() -> tuple[bool, str]:
        try:
            previous, _ = stop_calibration(config.artifact_dir)
            return True, build_stop_summary(previous)
        except Exception as exc:
            return False, str(exc)

    def _calibration_watch_interval() -> int:
        control = load_control(config.artifact_dir)
        return control.interval_seconds if control.interval_seconds > 0 else DEFAULT_CALIBRATION_INTERVAL_SECONDS

    def _status_check() -> tuple[bool, str]:
        try:
            probe = np.zeros(int(config.sample_rate * config.window_seconds), dtype=np.float32)
            primary = primary_backend.score(audio_window=probe, sample_rate=config.sample_rate)
            verifier_used = verifier_backend is not None
            if verifier_backend is not None:
                verifier = verifier_backend.score(audio_window=probe, sample_rate=config.sample_rate)
                baby_score = verifier.baby_score
                cat_score = verifier.cat_score
            else:
                baby_score = primary.baby_score
                cat_score = primary.cat_score

            gpu_ok, gpu_detail = run_gpu_check()
            gpu_state = f"gpu=ready({gpu_detail})" if gpu_ok else f"gpu=unavailable({gpu_detail})"
            mic_ok, mic_detail = probe_audio_input(device=config.audio_device)
            mic_state = f"mic=ready({mic_detail})" if mic_ok else f"mic=unavailable({mic_detail})"

            details = (
                "api=up classifier_cpu=ready "
                f"primary={primary.primary_score:.2f} baby={baby_score:.2f} cat={cat_score:.2f} "
                f"verifier={'on' if verifier_used else 'off'} {gpu_state} {mic_state}"
            )
            return True, details
        except Exception as exc:
            return False, f"classifier check failed: {exc}"

    def _send_test_sample(chat_id: str) -> tuple[bool, str]:
        try:
            clip_path, mode = capture_audio_clip(
                seconds=config.telegram_test_seconds,
                sample_rate=config.sample_rate,
                output_dir=config.artifact_dir,
                device=config.audio_device,
            )
            notifier.send_direct_clip(
                chat_id=chat_id,
                clip_path=clip_path,
                caption="Microphone test sample",
            )
            return True, f"sent {clip_path.name} via {mode}"
        except Exception as exc:
            return False, f"failed to capture/send sample: {exc}"

    poller = TelegramStartPoller(
        bot_token=config.telegram_bot_token,
        notifier=notifier,
        accept_new_users=config.accept_new_users,
        status_check=_status_check,
        test_sender=_send_test_sample,
        enable_test_command=config.enable_telegram_test_command,
        calibration_help_text=build_calibration_help_text,
        calibration_start=_calibration_start,
        calibration_set=_calibration_set,
        calibration_params=_format_calibration_params,
        calibration_status=_format_calibration_status,
        calibration_stop=_calibration_stop,
        calibration_watch_interval=_calibration_watch_interval,
    )

    @app.on_event("startup")
    def startup_event() -> None:
        if config.enable_telegram_poller:
            poller.start()

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        if config.enable_telegram_poller:
            poller.stop()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/classify")
    async def classify(file: UploadFile = File(...)):
        import librosa

        suffix = Path(file.filename or "clip.wav").suffix or ".wav"
        tmp_path = Path(config.artifact_dir) / f"upload{suffix}"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(await file.read())

        audio, sr = librosa.load(str(tmp_path), sr=config.sample_rate, mono=True)
        primary = primary_backend.score(audio_window=np.asarray(audio, dtype=np.float32), sample_rate=sr)

        final = primary
        verifier_used = False
        if verifier_backend is not None:
            verifier = verifier_backend.score(audio_window=np.asarray(audio, dtype=np.float32), sample_rate=sr)
            verifier_used = True
            final = DetectionResult(
                primary_score=primary.primary_score,
                baby_score=verifier.baby_score,
                cat_score=verifier.cat_score,
            )

        decision = passes_verifier(config=config, result=final)
        payload = {
            "decision": "baby" if decision else "cat_or_other",
            "primary_score": round(final.primary_score, 4),
            "baby_score": round(final.baby_score, 4),
            "cat_score": round(final.cat_score, 4),
            "verifier_used": verifier_used,
        }
        return JSONResponse(payload)

    @app.post("/telegram/start")
    async def telegram_start(chat_id: str):
        if not config.enable_manual_registration:
            return JSONResponse({"status": "disabled", "reason": "manual registration disabled"}, status_code=404)

        added = notifier.register_chat_id(chat_id=chat_id, accept_new_users=config.accept_new_users)
        if not added:
            try:
                notifier.send_direct_text(chat_id, "Registration is currently closed.")
            except Exception:
                pass
            return JSONResponse({"status": "rejected", "reason": "new users disabled"}, status_code=403)
        try:
            notifier.send_direct_text(chat_id, "Registration successful. You will receive baby-cry alerts.")
        except Exception:
            pass
        return JSONResponse({"status": "registered", "chat_id": chat_id})

    @app.post("/telegram/webhook")
    async def telegram_webhook(update: dict):
        message = update.get("message") or {}
        text = str(message.get("text", "")).strip()
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", "")).strip()

        if not text.startswith("/start"):
            return JSONResponse({"status": "ignored", "reason": "not_start_command"})
        if not chat_id:
            return JSONResponse({"status": "ignored", "reason": "missing_chat_id"}, status_code=400)

        added = notifier.register_chat_id(chat_id=chat_id, accept_new_users=config.accept_new_users)
        if not added:
            try:
                notifier.send_direct_text(chat_id, "Registration is currently closed.")
            except Exception:
                pass
            return JSONResponse({"status": "rejected", "reason": "new users disabled"}, status_code=403)
        try:
            notifier.send_direct_text(chat_id, "Registration successful. You will receive baby-cry alerts.")
        except Exception:
            pass
        return JSONResponse({"status": "registered", "chat_id": chat_id, "source": "telegram_start"})

    return app


app = create_app()


def main() -> int:
    import uvicorn

    uvicorn.run("baby_cry_detection.monitor.api:app", host="0.0.0.0", port=8080)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
