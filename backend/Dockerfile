# AutoDraw 2D backend — FastAPI + build123d (OpenCascade)
# Build:  docker build -t autodraw-backend ./backend
# Run:    docker run -p 8000:8000 --env-file backend/.env autodraw-backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CACHE_DIR=/app/cache

# Shared libs the OpenCascade / VTK wheels (cadquery-ocp) load at import time
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libx11-6 libxrender1 libxext6 libsm6 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Analyse the built-in samples now (build machines are fast) so they open
# instantly on low-CPU hosts whose disk is wiped on every spin-down.
RUN python -m scripts.warm_cache

# Unprivileged runtime user; the part cache stays writable for uploads
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser /app/cache
USER appuser
ENV HOME=/home/appuser

# Render / Railway / Fly inject $PORT; 8000 for local runs
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"

# --proxy-headers so per-IP rate limits see the real client IP behind the platform proxy
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
