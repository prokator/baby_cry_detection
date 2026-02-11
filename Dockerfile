FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libportaudio2 libpulse0 pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-monitor.txt /app/requirements-monitor.txt
RUN pip install --no-cache-dir -r /app/requirements-monitor.txt

COPY . /app
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "baby_cry_detection.monitor.cli"]
CMD ["status"]
