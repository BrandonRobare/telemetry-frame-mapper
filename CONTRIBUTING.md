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
- `@playcanvas/splat-transform`: required only for the splat cleanup/compress endpoints. Its exact version is pinned and locked in `tools/splat-transform/`; install it once with `npm ci --prefix tools/splat-transform` (Node.js >= 22). The backend runs it with `npx --no-install` from that directory and never downloads it at run time.

CI mocks every external binary and optional reconstruction library, so no test needs a real ffmpeg, exiftool, COLMAP, or GPU. Before a release, run the CLI once against real `ffmpeg`/`exiftool`; COLMAP, gsplat, SuGaR and video-render checks stay manual.

## Database migrations

The backend's SQLite schema is managed with Alembic. Migration scripts live in `backend/db/migrations/versions/`, configured via `alembic.ini` at the repo root and `backend/db/migrations/env.py`.

`init_db()` (in `backend/db/database.py`) runs automatically on every app startup and applies migrations for you — there is no manual step for normal use. A genuinely fresh database gets its schema created directly and is stamped as already migrated; an existing database is upgraded to the latest revision. Both paths converge on the same schema: the baseline revision `0001` is a frozen copy of the schema that never follows `models.py`, and every later revision applies its change to fresh and existing databases alike. `tests/backend/test_database.py` fails when a fresh `alembic upgrade head`, or an upgrade of a released schema, stops matching the models.

To add a schema change:

1. Update the SQLAlchemy models in `backend/db/models.py`.
2. Generate a migration: `alembic revision --autogenerate -m "describe the change"`. Never edit `0001_baseline.py` or reuse a shipped revision ID; installs store the ID they reached.
3. Review the generated file under `backend/db/migrations/versions/` — autogenerate is a starting point, not the final word, especially for SQLite (which has limited `ALTER TABLE` support). Changing the constraints of an existing table, or dropping a constrained column, needs `op.batch_alter_table`, which rebuilds the table; `env.py` turns off SQLite's foreign-key enforcement while migrations run so that rebuild cannot fail on, or cascade into, rows in other tables.
4. Run the app or test suite locally to confirm `init_db()` applies the new migration cleanly against both a fresh DB and your existing local DB.

## Test gates

```bash
uv run --no-sync python tests/test_supply_chain_configuration.py
uv run --no-sync pytest
uv run --no-sync ruff check .
cd frontend && npm test -- --run
```

Tests must assert clear, actionable failures for missing external tools instead of raw `FileNotFoundError`, traceback-only import failures, or silent hard imports.

## API and export contracts

Backend schemas are the source of frontend wire types. After a public schema change, run
from the repository root:

```bash
uv run --frozen --no-sync python -m tools.openapi_snapshot
npm --prefix frontend run api:generate
uv run --frozen --no-sync pytest tests/contract
npm --prefix frontend run api:check
```

Commit both `frontend/openapi.json` and `frontend/src/types/api.generated.ts`. The Python
CI lane compares the snapshot with `app.openapi()`; the frontend lane regenerates types
in memory and compares the checked-in file. Both checks fail on drift without changing files.
`api.ts` preserves public frontend names as aliases; settings form types select editable
fields from the generated response types. New dictionary response schemas use FastAPI
`responses` metadata to preserve existing serialization. CSV column and GeoJSON property
fixtures live in `tests/contract/fixtures/export_schemas.json`, including browser frame exports.
