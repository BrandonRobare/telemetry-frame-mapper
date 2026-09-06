# Contributing

## Development setup

```bash
uv sync --group backend --group dev
cd frontend && npm install
```

For CLI-only development, `uv sync --group dev` is enough. These are PEP 735 dependency groups for
a source checkout, not wheel extras: pip's extra syntax cannot install them. The published wheel
contains only the CLI package.

## External tools and optional dependencies

Required for the CLI:

- `ffmpeg`: required when extracting DJI SRT telemetry from MP4 files. It must be on `PATH` or passed with `--ffmpeg`.
- `exiftool`: required when writing GPS EXIF tags. It must be on `PATH` or passed with `--exiftool`.

Optional, for reconstruction:

- `colmap`: required only for Reconstruct tab SfM jobs.
- `gsplat` plus a CUDA-capable GPU: required for Gaussian splat training and optional server-side rendering hooks. Run `uv sync --group backend --group reconstruction --group dev` when validating reconstruction locally. Missing thumbnail renderer support should not break backend import or COLMAP-only setup.
- SuGaR (`sugar_scene`/`sugar`): required only for mesh export. It is not included in the `reconstruction` dependency group because there is no installable `sugar`/`sugar-scene` PyPI package; install it from the upstream SuGaR project for manual mesh-export smoke.
- Server-side flythrough rendering is optional; when the gsplat video renderer is unavailable, users can use browser recording.

CI mocks every external binary and optional reconstruction library, so no test needs a real ffmpeg, exiftool, COLMAP, or GPU. Before a release, run the CLI once against real `ffmpeg`/`exiftool`; COLMAP, gsplat, SuGaR and video-render checks stay manual.

## Database migrations

The backend's SQLite schema is managed with Alembic. Migration scripts live in `backend/db/migrations/versions/`, configured via `alembic.ini` at the repo root and `backend/db/migrations/env.py`.

`init_db()` (in `backend/db/database.py`) runs automatically on every app startup and applies migrations for you — there is no manual step for normal use. A genuinely fresh database gets its schema created directly and is stamped as already migrated; an existing database is upgraded to the latest revision. Both paths converge on the same schema because the baseline migration is idempotent.

To add a schema change:

1. Update the SQLAlchemy models in `backend/db/models.py`.
2. Generate a migration: `alembic revision --autogenerate -m "describe the change"`.
3. Review the generated file under `backend/db/migrations/versions/` — autogenerate is a starting point, not the final word, especially for SQLite (which has limited `ALTER TABLE` support).
4. Run the app or test suite locally to confirm `init_db()` applies the new migration cleanly against both a fresh DB and your existing local DB.

## Test gates

```bash
uv run --no-sync python tests/test_supply_chain_configuration.py
uv run --no-sync pytest
uv run --no-sync ruff check .
cd frontend && npm test -- --run
```

Tests must assert clear, actionable failures for missing external tools instead of raw `FileNotFoundError`, traceback-only import failures, or silent hard imports.
