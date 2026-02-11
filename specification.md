# Baby Cry Monitor Specification

## 1. Objective
Build an on-demand Dockerized application that listens to ambient audio near a laptop, detects likely baby crying events, and sends Telegram alerts. The system must run on a laptop with an NVIDIA RTX 2070 and prioritize low false positives from household cat sounds.

## 2. Scope
### In scope
- Real-time audio capture from a selected microphone device.
- Cry detection pipeline running in Docker with optional GPU acceleration.
- Telegram notifications for confirmed cry events.
- Telegram attachment of the audio snippet that triggered the alert.
- Configuration via environment variables and CLI flags.
- Logging and basic observability for local use.

### Out of scope (initial release)
- 24/7 cloud deployment.
- Mobile app UI.
- Continuous model retraining pipeline.
- Medical/safety guarantees.

## 3. Primary Use Case
Parent starts monitoring only when needed (for example at nap time), keeps the app running in foreground/background, and receives Telegram alerts when a baby cry is detected. Parent can stop monitoring at any time.

## 4. Key Requirements
### Functional requirements
1. Start/stop monitoring on demand from CLI (`start`, `stop`, `status` or equivalent).
2. Capture live audio in short windows (for example 0.96 s to 3 s frames with overlap).
3. Detect baby cry events with confidence score.
4. Reduce false positives from cat vocalizations and mixed scenes (cat + baby).
5. Trigger Telegram text notification with timestamp, confidence, and basic metadata.
6. Send the triggering audio clip file to Telegram (`sendDocument` or `sendAudio`).
7. Cooldown/debounce to avoid notification spam during one continuous crying episode.
8. Save local event artifacts (JSON metadata + WAV clip) for audit and tuning.

### Non-functional requirements
1. Must run in Docker on Windows host and use NVIDIA GPU when available.
2. Startup time target: under 20 seconds after image is available.
3. End-to-end alert latency target: under 5 seconds from event onset.
4. Reasonable CPU fallback if GPU is unavailable.
5. Secure secrets handling through `.env` (no hard-coded tokens).

## 5. Detection Approach Options
### Option A: Extend existing repository model
- Reuse current feature engineering and binary classifier flow.
- Add cat-negative class data and retrain or add post-filter logic.
- Pros: aligns with existing repo and code structure.
- Cons: likely weaker generalization to home acoustic diversity; requires more custom dataset work.

### Option B: YAMNet-based detector (recommended baseline)
- Use YAMNet embeddings/class scores for audio events.
- Build cry decision logic from relevant classes (baby cry/infant cry) plus cat classes as suppressors.
- Add temporal smoothing and decision fusion over sliding windows.
- Pros: strong pretrained general audio understanding, faster to baseline, explicit cat-related event handling.
- Cons: still needs threshold calibration for apartment/home noise conditions.

### Decision for initial implementation
- Keep the repository's existing detector path as the primary trigger (`existing_model`).
- Add YAMNet as an additional verification/suppression layer before alert emission.
- Keep backend abstraction so either path can be promoted to primary in later tuning rounds.
- Rationale: preserve already effective behavior while adding cat-aware filtering without replacing the core detector on day one.

## 6. Anti-Cat False Positive Strategy (critical)
Use multi-condition gating rather than a single threshold.

Decision on check order:
- Yes, cat-aware suppression is applied before alert emission.
- The event is promoted to alert only after baby-dominant persistence passes and cat-dominant suppression does not apply.

1. Compute per-window scores:
   - `baby_score`: aggregate probability of baby cry-related classes.
   - `cat_score`: aggregate probability of cat/meow-related classes.
   - `primary_score`: score or decision from the existing model path.
2. Trigger candidate only when:
   - `primary_score` indicates cry candidate (or exceeds configured threshold)
   - `baby_score >= BABY_THRESHOLD` from YAMNet verifier
   - `baby_score - CAT_WEIGHT * cat_score >= MARGIN_THRESHOLD`
3. Confirm event only if candidate persists for `N` of last `M` windows.
4. Suppress event when cat dominates (`cat_score >= CAT_SUPPRESS_THRESHOLD`) unless baby dominance remains strong for sustained period.
5. Add optional second-stage verifier on buffered clip (larger context window).

Calibration plan:
- Collect short local samples: baby cry, cat meow, mixed, TV/noise, silence.
- Tune thresholds to maximize recall while explicitly minimizing cat false alerts.
- Track confusion matrix with dedicated `cat -> baby` false positive metric.

## 7. Telegram Alerting Requirements
### Required behavior
1. Text alert message includes:
   - Event type (`baby_cry_detected`)
   - Local timestamp
   - Confidence score(s)
   - Optional host name/device id
2. Attach triggering clip (for example 5-10 s WAV/OGG).
3. If upload fails, retry once and log failure with reason.
4. Use bot token and chat/user id from environment.

### Suggested message format
`[Baby Monitor] Cry detected at 2026-02-10 22:14:05 (confidence=0.87, cat_score=0.12)`

## 8. Runtime and Docker Specification
### Container requirements
- Base image suitable for audio + ML inference (Python 3.10+).
- Dependencies: PyTorch/TensorFlow runtime (based on chosen model), audio IO libs, requests/python-telegram-bot.
- Runtime mounts:
  - Input audio device access.
  - Local `artifacts/` directory for clips and logs.
- Environment file support (`--env-file .env`).

### GPU requirements
- Docker must run with NVIDIA runtime and `--gpus all`.
- App auto-detects CUDA and logs whether GPU or CPU path is active.

### Suggested run command (draft)
`docker run --rm --gpus all --env-file .env -v ./artifacts:/app/artifacts <image> monitor start`

## 9. Configuration
Minimum `.env` variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `AUDIO_DEVICE` (default system mic if unset)
- `BABY_THRESHOLD`
- `CAT_WEIGHT`
- `MARGIN_THRESHOLD`
- `CAT_SUPPRESS_THRESHOLD`
- `WINDOW_SECONDS`
- `EVENT_CLIP_SECONDS`
- `ALERT_COOLDOWN_SECONDS`
- `LOG_LEVEL`

## 10. Event Flow
1. User starts monitor command.
2. Service initializes audio input, model, and Telegram client.
3. Service processes streaming windows and computes scores.
4. Gating logic determines candidate and confirmed events.
   - Cat suppression is evaluated before alert emission.
5. On confirmed event:
   - Persist clip + metadata locally.
   - Send Telegram text alert.
   - Send Telegram audio/document clip.
6. Apply cooldown and continue listening.
7. User stops command; app flushes buffers and exits cleanly.

## 11. Project Deliverables (implementation phase)
1. `specification.md` (this file).
2. Dockerized monitor app with CLI entrypoint.
3. Detection backend abstraction with two modes:
   - `existing_model` (primary)
   - `yamnet` (verification layer)
4. Telegram notifier module including clip upload.
5. Config module + `.env.example`.
6. Basic tests for config parsing, gating logic, and alert formatting.
7. Operator documentation in `README.md`.

## 12. Acceptance Criteria
1. App runs from Docker on demand and can be stopped safely.
2. Telegram receives text + clip for positive detection.
3. In local validation set, cat-only clips do not trigger alerts above agreed threshold.
4. Mixed clips with true baby cry still trigger with acceptable latency.
5. Logs and artifacts are sufficient to diagnose false positives/negatives.

## 13. Risks and Mitigations
- Risk: microphone access differences across host environments.
  - Mitigation: explicit audio device config and startup self-check.
- Risk: model drift across room acoustics.
  - Mitigation: local threshold calibration and saved event review.
- Risk: Telegram rate limits or connectivity issues.
  - Mitigation: cooldown, retries, and local event persistence.

## 14. Implementation Plan (high level)
1. Build minimal streaming pipeline + Telegram text alert.
2. Add clip buffering and clip upload to Telegram.
3. Integrate YAMNet baseline backend and cat-aware gating.
4. Add Docker + GPU runtime config.
5. Run local tuning session with cat/baby/mixed recordings.
6. Finalize docs and operational runbook.

## 15. Efficiency Estimate (Primary Model + YAMNet Verifier)
These are planning estimates for on-demand monitoring and must be validated during implementation.

- Inference cadence: 0.96 s windows with overlap (up to ~3 inferences/sec depending on hop size).
- RTX 2070 expectation: real-time inference with significant headroom for gating and buffering.
- CPU fallback expectation: still real-time for single microphone stream, with higher latency variance.
- Estimated alert latency: typically 2-5 s including primary detection, verifier gating, and Telegram send.
- Memory footprint target: under 1 GB container RSS during steady-state monitoring.
- Bottlenecks to monitor: audio IO jitter, Telegram network delays, and clip encoding/upload time.

Validation plan:
- Capture processing-time metrics per window (`t_capture`, `t_infer`, `t_gate`, `t_notify`).
- Track P50/P95 end-to-end alert latency in local trial sessions.
- Compare GPU vs CPU run profiles and document observed throughput.
