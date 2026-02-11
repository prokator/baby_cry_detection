# Baby Cry Detection - Updated Project Overview

## Original Project

This repository is a fork/extension of the original baby-cry detection project focused on model training on PC and prediction flow for Raspberry Pi.

The original README is preserved as [`ORIGINAL_README.md`](ORIGINAL_README.md).

## Why This Fork Exists

The fork was created to turn the original research/prototype code into an operational, on-demand monitoring system for real home use:

- run fully in Docker on Windows + WSL environments
- reduce false positives with multi-stage verification
- send actionable Telegram alerts with audio clips
- support practical calibration and service lifecycle control from scripts/commands

This new README describes what has been added on top of the original codebase.

## What Changed From Original Version

- Added a Docker-first real-time monitoring stack.
- Added Telegram alerting with text + audio clip delivery.
- Added anti-false-positive detection flow with a two-stage pipeline:
  - phase 1: existing model/gating
  - phase 2: verifier/suppression layer (YAMNet-based path)
- Added runtime calibration controls from Telegram commands.
- Added service lifecycle scripts for manual start/stop operation.
- Added richer monitor-oriented tests and operational docs.

## Current Architecture

- `monitor` service: continuous audio listening and detection loop.
- `monitor-api` service: API endpoints + Telegram bot polling commands.
- Shared `artifacts/` volume: stores trigger clips, event metadata, and calibration state files used by both services.

## Major Additions

### 1) Docker + Compose Runtime

- `Dockerfile`
- `docker-compose.yml`
- `start_service.bat` / `stop_service.bat`
- Pulse bridge helper scripts for Docker-on-Windows + WSL microphone access:
  - `refresh_pulse_bridge.bat`
  - `list_mics.bat`

### 2) Monitor Package

New/extended monitor modules under `baby_cry_detection/monitor/`:

- `cli.py` - live monitor loop and command entrypoint.
- `api.py` - FastAPI app + Telegram poller wiring.
- `audio.py` - resilient audio capture (PortAudio + Pulse fallback).
- `service.py`, `gating.py`, `decision.py` - detection and gating logic.
- `notifier.py`, `recipient_store.py`, `telegram_poller.py` - Telegram messaging and command processing.
- `calibration.py` - shared calibration control/status and command help utilities.
- `backends/*` - primary/verifier backend abstractions and implementations.

### 3) Telegram Bot Commands

Core commands:

- `/start`
- `/status`
- `/test`

Calibration commands:

- `/cal`
- `/cal_start phase1 [interval_sec]`
- `/cal_start phase2 [interval_sec]`
- `/cal_set <param> <value>`
- `/cal_params`
- `/cal_status`
- `/cal_watch [interval_sec]`
- `/cal_watch_stop`
- `/cal_stop`

Calibration behavior:

- Alerts are suppressed while calibration is active.
- Periodic detection snapshots are produced for tuning.
- On `/cal_stop`, runtime returns to `.env` defaults and alerts are re-enabled.

### 4) Configuration

Use `.env.example` as the template for local `.env`.

Important categories:

- Telegram: token/chat/poller/test controls
- Audio: sample rate, device, pulse settings, mic gain
- Detection thresholds: phase1 + phase2 tuning parameters
- Runtime: cooldown, artifact path, backend toggles, logging

## Quick Start (Updated Stack)

1. Copy `.env.example` to `.env` and fill required values (especially Telegram token/chat).
2. Build image:

```bash
docker build -t baby-cry-monitor .
```

3. Start full stack:

```bat
start_service.bat
```

4. Stop full stack:

```bat
stop_service.bat
```

## API Endpoints (monitor-api)

- `GET /health`
- `POST /classify`
- `POST /telegram/start`
- `POST /telegram/webhook`

## Test Coverage Added

Monitor-focused tests now include:

- config parsing
- gating behavior
- notifier behavior
- CLI logic
- Telegram poller commands
- calibration state and command behavior
- backend integration checks

## Notes

- The original training/prediction project structure is still present.
- This update layers an operational monitoring system on top of the original repository.
