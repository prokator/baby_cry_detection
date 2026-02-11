# Baby cry detection - Building the model
### Recognition of baby cry from audio signals

The aim is to automatically recognize a baby crying while sleeping. In such case, a lullaby is played to calm the baby
down.

This is done by implementing a machine learning algorithm on a Raspberry Pi. The idea is to train a model on a computer
and to deploy it on Raspberry Pi, which is used to record a signal and use the model to predict if it is a baby cry or
not. In the former case a lullaby is played, in the latter the process (recording and predicting steps) starts again.

### Code organisation

The code is organised as follows.

- `./baby_cry_detection/pc_main` and `./baby_cry_detection/pc_methods` folders: to run on a computer, they implement the training part
- `./baby_cry_detection/rpi_main` and `./baby_cry_detection/rpi_methods` folders: to run on a Raspberry Pi, they implement the predicting part


##### TRAINING

It includes all the steps required to train a machine learning model. First, it reads the data, it performs feature
engineering and it trains the model.

The model is saved to be used in the prediction step. The _training step_ is performed
on a powerful machine, such as a personal computer.

Code to run this part is included in `pc_main` and `pc_methods`.

##### PREDICTION

It includes all the steps needed to make a prediction on a new signal. It reads a new signal (9 second long), it cuts
it into 5 overlapping signals (5 second long), it applies the pipeline saved from the training step to make a
prediction.

The _prediction_ step is performed on a Raspberry Pi 2B. Please check
[baby_cry_rpi](https://github.com/giulbia/baby_cry_rpi.git) for deployment on Raspberry Pi.

Code to run this part is included in `rpi_main` and `rpi_methods`.

##### SIMULATION

There is a script to test the prediction step on your computer before deployment on Raspberry Pi.

A script `prediction_simulation.py` and 2 audio signals are provided in folder `./baby_cry_detection/prediction_simulation`.

### Run

To make it run properly, clone this repo in a folder. In the same parent folder you should also create the following
tree structure:
* PARENT FOLDER
  * baby_cry_detection *this cloned repo*
  * output
    * dataset
    * model
    * prediction
  * recording

From your command line go to baby_cry_detection folder and run the following python scripts.

##### TRAINING

This step allows you to train the model. Please note that the model itself is not provided.

```
# Create and save trainset
python baby_cry_detection/pc_main/train_set.py
```
```
# Train and save model
python baby_cry_detection/pc_main/train_model.py
```

Script `train_set.py` saves the trainset in folder _dataset_ and, script `train_model.py` saves the model in folder
 _model_. Folders _dataset_ and _model_ are parameters with default values that fits with the organisation shown
 above, they can be changed as wished.

##### PREDICTION

This step is to be executed on Raspberry Pi. Please refer to [baby_cry_rpi](https://github.com/giulbia/baby_cry_rpi.git)

##### SIMULATION

This step allows you to test the model on your computer. It uses scripts from `rpi_methods` folder.

```
python baby_cry_detection/prediction_simulation/prediction_simulation.py
```

### Logs

Log files are created for each step, they are saved in folder `baby_cry_detection`.




>Part of the data used for training comes from
[ESC-50: Dataset for environmental sound classification](https://github.com/karoldvl/ESC-50)

## Docker monitor prototype

An on-demand monitoring prototype is available under `baby_cry_detection/monitor`.

### Quick start

1. Copy `.env.example` to `.env` and fill `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
2. Build image:

```bash
docker build -t baby-cry-monitor .
```

3. Run dry-run mode:

```bash
docker run --rm --env-file .env -v ./artifacts:/app/artifacts baby-cry-monitor start --dry-run
```

For GPU hosts, add `--gpus all` at runtime.

### Live mode

```bash
docker run --rm --env-file .env -v ./artifacts:/app/artifacts baby-cry-monitor start
```

Optional `--max-windows N` helps run short calibration sessions.

Debug option: set `DEBUG_CLASSIFIER_ONLY_MODE=true` in `.env` to bypass first-stage gating.
In this mode, the monitor scores every 5-second audio block once per 15-second cycle and logs pass/fail with model scores.

Detection flow in live mode uses primary screening first, then runs the verifier on the buffered trigger clip before sending Telegram alert.
YAMNet is used only as second-stage verifier (not continuous first-stage inference) to reduce GPU/compute utilization.

Optional: set `ENABLE_OLLAMA_VALIDATOR=true` to add a host Ollama policy check on model scores before alert send.

StdHuman Telegram auth settings are also included in `.env`:
- `DEV_TELEGRAM_USERNAME` for fixed authorized user
- `ACCEPT_NEW_USERS` to allow or block new `/start` authorizations at service side
- `RECIPIENT_STORE_PATH` to persist accepted Telegram chat IDs

### GPU check

```bash
docker run --rm --gpus all --env-file .env baby-cry-monitor gpu-check
```

### Cat vs child classifier API (container service)

Run service:

```bash
docker run --rm --entrypoint python --env-file .env -p 8080:8080 -v ./artifacts:/app/artifacts baby-cry-monitor -m baby_cry_detection.monitor.api
```

Classify uploaded clip:

```bash
curl -X POST http://localhost:8080/classify -F "file=@path/to/clip.wav"
```

Register chat ID when `ACCEPT_NEW_USERS=true`:

```bash
curl -X POST "http://localhost:8080/telegram/start?chat_id=<telegram_chat_id>"
```

Telegram long-polling is the main `/start` handling flow (`ENABLE_TELEGRAM_POLLER=true`), so webhook setup is optional.
If needed, Telegram-style webhook payloads are also accepted at `POST /telegram/webhook`.

Telegram bot commands handled by poller:
- `/status` reports API readiness, CPU classifier check, and GPU availability (`nvidia-smi`).
- `/test` records a short microphone sample and sends it back to the requesting user.
- `/cal` shows calibration help and clickable calibration commands.
- `/cal_start phase1 [interval_sec]` starts phase-1 calibration (alerts suppressed while calibration is active).
- `/cal_start phase2 [interval_sec]` starts phase-2 calibration (full flow runs, phase1 assumed calibrated, alerts still suppressed).
- `/cal_set <param> <value>` updates calibration parameters for the active phase.
- `/cal_params` returns current effective calibration parameters.
- `/cal_status` returns current detection state snapshot for calibration.
- `/cal_watch [interval_sec]` streams calibration status updates until stopped.
- `/cal_watch_stop` stops periodic calibration status updates.
- `/cal_stop` ends calibration, restores `.env` parameters, re-enables alerts, and returns replayable command state.

`/test` is controlled by `ENABLE_TELEGRAM_TEST_COMMAND` and sample length is set by `TELEGRAM_TEST_SECONDS`.
Recorded clips are converted to MP3 before Telegram upload for Android playback compatibility.

Calibration phase parameter scope:
- phase1: `PRIMARY_CRY_THRESHOLD`, `CONFIRM_N`, `CONFIRM_M`, `ALERT_COOLDOWN_SECONDS`
- phase2: `CRY_THRESHOLD`, `CAT_THRESHOLD`, `CAT_WEIGHT`, `MARGIN_THRESHOLD`

Calibration status is shared through files in `ARTIFACT_DIR` so `monitor` and `monitor-api` containers stay synchronized.

Microphone sensitivity can be increased with software preamp:
- `MIC_GAIN_DB` (range clamped to -30..+30 dB)
- Example high sensitivity: `MIC_GAIN_DB=30`

Cry/cat tuning parameters:
- `PRIMARY_CRY_THRESHOLD` controls first-stage cry confidence gate
- `CRY_THRESHOLD` controls baby-cry verifier threshold
- `CAT_THRESHOLD` controls cat suppression threshold
- `CAT_WEIGHT` and `MARGIN_THRESHOLD` control cry-vs-cat margin behavior
- `NON_CRY_WEIGHT` increases suppression for strong non-cry classes (speech, TV, appliances, etc.)

If container has no direct microphone device, configure PulseAudio bridge for Docker:
- run a WSL bridge service so Docker can reach WSLg Pulse socket:

```bash
wsl -d Ubuntu -u root -- bash -lc "cat > /etc/systemd/system/wslg-pulse-bridge.service <<'EOF'
[Unit]
Description=Bridge WSLg Pulse socket to TCP 4713
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:4713,fork,reuseaddr UNIX-CONNECT:/mnt/wslg/PulseServer
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now wslg-pulse-bridge.service"
```

- set `PULSE_SERVER=tcp:<WSL_UBUNTU_IP>:4713` (`hostname -I` inside WSL)
- optionally set `PULSE_SOURCE` (default: `default`)

Windows helper script to automate bridge + env update + container restart:

```bat
refresh_pulse_bridge.bat
```

Optional distro arg:

```bat
refresh_pulse_bridge.bat Ubuntu
```

List available microphone sources/devices:

```bat
list_mics.bat
```

To target a specific microphone:
- Pulse bridge mode (recommended on Docker Desktop Windows): set `PULSE_SOURCE` to a source from `list_mics.bat`.
- Direct container device mode: set `AUDIO_DEVICE` to the PortAudio id/name visible in the container.

`/status` now reports microphone availability (`mic=...`) to show whether `/test` can capture audio.

Compose shortcuts:

```bash
docker compose up monitor
docker compose up monitor-api
```

## E2E Service Control (single compose block)

The monitoring stack is managed as one compose group (`monitor` + `monitor-api`) in `docker-compose.yml`.

Start full E2E stack (checks WSL, refreshes pulse bridge, updates `.env`, starts all services):

```bat
start_service.bat
```

Optional distro arg:

```bat
start_service.bat Ubuntu
```

Stop all monitoring-related services (Docker stack + WSL pulse bridge) and keep manual-only activation policy:

```bat
stop_service.bat
```

After reboot, services do not auto-start. Use `start_service.bat` manually when you want monitoring active.
