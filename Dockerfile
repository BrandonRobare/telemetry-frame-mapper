# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

# Images are pinned by digest; the tag stays for readers and Dependabot's docker updates.
FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
COPY frontend/scripts/api-types/package.json ./scripts/api-types/package.json
RUN npm ci
COPY frontend/ ./
COPY tests/contract/fixtures/export_schemas.json /app/tests/contract/fixtures/export_schemas.json
RUN npm run build

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DEPLOYMENT_HOST=0.0.0.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        colmap \
        ffmpeg \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
COPY backend/ ./backend/
COPY config.yaml ./config.yaml
# init_db() resolves alembic.ini relative to the repo root and runs `upgrade head`
# against it at startup, so the container will not boot without this.
COPY alembic.ini ./alembic.ini
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN uv sync --frozen --no-dev --group backend --group reconstruction --group semantic

# Run the API as an unprivileged user (UID/GID 1000). Code and the virtualenv stay root-owned.
# The user owns only what the app writes at runtime: the data/drop/derived/export and log
# directories, and /app itself, where Settings atomically replaces config.yaml and the share
# signing key is created beside exports/.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p data imports processed exports logs \
    && chown app:app /app /app/config.yaml /app/data /app/imports /app/processed /app/exports /app/logs

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["python", "-m", "backend"]
