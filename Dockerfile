# Viral Clip — FastAPI + ffmpeg + yt-dlp
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    MAX_DURATION_SEC=7200 \
    MOCK_ANALYZE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      fonts-dejavu-core \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY web.html ./web.html
COPY demo ./demo
RUN sh scripts/generate_demo.sh /app/demo/muestra_45s.mp4

RUN mkdir -p /data/jobs /data/fixtures \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8741

# Railway/Render/Fly inject PORT; default to 8741 for local docker runs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8741}"]
