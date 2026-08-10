# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        colmap \
        ffmpeg \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
COPY backend/ ./backend/
COPY config.yaml ./config.yaml
# init_db() resolves alembic.ini relative to the repo root and runs `upgrade head`
# against it at startup, so the container will not boot without this.
COPY alembic.ini ./alembic.ini
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN pip install --upgrade pip \
    && pip install "uv==0.11.16" \
    && uv sync --frozen --no-dev --group backend --group reconstruction

ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p data imports processed exports

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["sh", "-c", "uvicorn backend.main:app --host ${HOST} --port ${PORT} --workers 1"]
