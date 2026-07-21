FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY agent ./agent
COPY tests ./tests

EXPOSE 8080

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
