FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-web.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt -r requirements-web.txt

COPY *.py ./
COPY webapp ./webapp

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app
