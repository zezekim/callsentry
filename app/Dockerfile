FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel && pip install ".[dev]"

COPY alembic.ini ./
COPY alembic ./alembic
COPY callsentry ./callsentry
COPY tests ./tests

RUN pip install --no-deps -e .

EXPOSE 8000

CMD ["uvicorn", "callsentry.main:app", "--host", "0.0.0.0", "--port", "8000"]
