# SEO Suite — production image.
# Based on the official Playwright Python image so the indexing feature's
# Chromium browser is available out of the box.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure the Chromium build matches the installed Playwright version.
RUN python -m playwright install chromium

COPY . .

# Data (reports, uploads, users.json) is written here. Mount a persistent
# volume at /app/data on your host so it survives restarts/redeploys.
ENV SEO_SUITE_DATA_DIR=/app/data \
    SEO_SUITE_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /app/data

EXPOSE 8080

# IMPORTANT: a single worker with threads.
# Run state (run status, SSE subscriber queues) lives in process memory, so the
# app must run as ONE process. Threads handle concurrency + SSE streaming.
# Shell form so ${PORT} (set by Render/Fly) is expanded; falls back to 8080.
CMD gunicorn --workers 1 --threads 8 --worker-class gthread --timeout 300 \
    --bind 0.0.0.0:${PORT:-8080} app.server:app
