FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf

WORKDIR /srv

# ffmpeg decodes Twilio's mu-law recordings; espeak-ng is Kokoro's g2p backend.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY worker ./worker

RUN mkdir -p /models

EXPOSE 8100

CMD ["uvicorn", "worker.main:app", "--host", "0.0.0.0", "--port", "8100"]
