# Installation

What you need depends on how much of the pipeline you use:

| You want to… | You need |
|---|---|
| Geotag video frames (CLI only) | Python 3.10+, `ffmpeg`, `exiftool` |
| Use the web app (map, review, plan, export) | + Node 18+, the `[backend]` Python extra |
| Run 3D reconstruction | + COLMAP on PATH |
| Train gaussian splats / render server-side | + NVIDIA GPU (4 GB+ VRAM), CUDA toolkit, torch + gsplat (see [SETUP.md](SETUP.md)) |

**Hardware guidance:** any modern machine handles the CLI and web app. COLMAP benefits from a GPU but runs CPU-only (slowly). Splat training requires an NVIDIA GPU; 4 GB VRAM works with the `quick` preset and capped scene sizes, 8 GB+ is comfortable for `full`. 16 GB system RAM recommended when training (frame cache).

## 1. Python package

```bash
git clone https://github.com/BrandonRobare/telemetry-frame-mapper.git
cd telemetry-frame-mapper
python -m venv .venv
# Windows:  .venv\Scripts\activate     Linux/macOS:  source .venv/bin/activate

pip install -e ".[backend,dev]"   # CLI + web backend + test tools
# or, CLI only:
pip install -e ".[dev]"
```

Verify: `drone-video-geotagger --help` and `pytest` (all tests should pass without any external binaries installed).

## 2. External binaries

The CLI shells out to `ffmpeg` and `exiftool`; reconstruction shells out to `colmap`. Each must be on `PATH` (the CLI also accepts `--ffmpeg` / `--exiftool` paths explicitly).

### Windows

```powershell
winget install Gyan.FFmpeg
winget install OliverBetz.ExifTool
```

- If you install ffmpeg manually (e.g. to `C:\ffmpeg`), add `C:\ffmpeg\bin` to PATH.
- winget installs ExifTool to `%LOCALAPPDATA%\Programs\ExifTool` and registers it on PATH; open a new terminal afterwards.
- **COLMAP:** download the Windows release zip from [github.com/colmap/colmap/releases](https://github.com/colmap/colmap/releases) (pick the CUDA build if you have an NVIDIA GPU), extract (e.g. to `C:\colmap`), and add its `bin` folder to PATH.

### Linux (Debian/Ubuntu)

```bash
sudo apt install ffmpeg libimage-exiftool-perl colmap
```

(The distro `colmap` package is CPU-only on some releases; build from source or use the flatpak for CUDA support.)

### macOS

```bash
brew install ffmpeg exiftool colmap
```

Verify all three:

```bash
ffmpeg -version
exiftool -ver
colmap -h
```

## 3. Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

Requires Node 18+. The UI expects the backend at `http://localhost:8000` (override with a `VITE_API_URL` env var).

## 4. Run it

From the **repo root** (paths in `config.yaml` resolve relative to it):

```bash
uvicorn backend.main:app --reload    # API: http://localhost:8000, docs: /docs
```

First run creates `data/drone_mapping.db` (SQLite — set `DATABASE_URL` to use PostgreSQL instead). Optional mission parameters (camera FOV, overlap targets, CRS, directories) live in [config.yaml](../config.yaml).

### Optional local PIN lock

For a single-user deployment on a trusted local network, set `pin_lock.enabled: true` in
`config.yaml`. The PIN itself never goes in YAML. Generate an scrypt hash without putting the
PIN in shell history, then set the named environment variable before starting the backend:

```powershell
$env:DRONE_MAPPING_PIN_HASH = python -c "from getpass import getpass; from backend.services.share_links import hash_password; print(hash_password(getpass('PIN: ')))"
```

The prompt does not echo or store the PIN in shell history. Use a persistent secret manager or
service environment for production; the PowerShell assignment above lasts only for that shell.
While enabled, every API endpoint, the browser app and its static
assets, `/processed` files, and share routes require an unlock cookie. `/health` and FastAPI docs
remain available for operations. Unlock with `POST /pin-lock/unlock` JSON `{"pin":"..."}`; a
successful `204` sets an HttpOnly, SameSite=Lax cookie valid for `session_ttl` seconds (8 hours by
default). Check only the non-secret state at `GET /pin-lock/status`. Restarting the backend clears
all unlock sessions. If the configured hash environment variable is absent, the backend refuses to
start rather than silently running unlocked.

### Optional automation API key

For scripts that cannot retain the PIN unlock cookie, enable `api_key.enabled: true` alongside
`pin_lock.enabled: true`. The key is an alternative credential for the same protected routes; it
does not create a separate authentication system or make an otherwise-unlocked app private. Store
only its scrypt hash in the named environment variable:

```powershell
$env:DRONE_MAPPING_API_KEY_HASH = python -c "from getpass import getpass; from backend.services.share_links import hash_password; print(hash_password(getpass('API key: ')))"
```

The prompt does not echo or store the key in shell history. After restarting the backend, send the
plain key only in the `X-Drone-Mapping-Key` request header, for example:

```powershell
curl.exe -H "X-Drone-Mapping-Key: your-key" http://127.0.0.1:8000/sessions
```

Never put the plain key in `config.yaml`, a URL, or a script committed to source control. To revoke
it, replace the environment variable with a newly generated hash and restart the backend; every
previous key immediately stops working. An enabled API-key block without an enabled, valid PIN lock
is rejected at startup. `/metrics` intentionally remains unauthenticated for local Prometheus
scraping, exactly as documented below.

### Prometheus metrics

`GET /metrics` remains reachable without an unlock cookie, including while the optional PIN lock
is enabled, so a local scraper can check it. Keep the default loopback bind; if the backend is
exposed on a LAN, protect this endpoint with a reverse proxy or firewall. It returns Prometheus
text exposition with the fixed application version, process start time, and a lightweight `SELECT
1` database probe. It deliberately emits no project, file, user, or location data and does not
scan application tables.

## 5. GPU splat training (optional)

Torch and gsplat are **deliberately not** in the pip extras — CUDA-enabled torch is not on the default PyPI index, and gsplat must compile against your torch/CUDA combination. Follow the step-by-step in [SETUP.md](SETUP.md). Without them, everything still works except splat training itself: reconstructions complete in `colmap_only` mode.

## Uninstall / clean state

All state is local and file-based: delete `data/` (database), `processed/` (thumbnails), `exports/` (outputs), and `imports/` (your images) to reset. `pip uninstall drone-video-geotagger` removes the package.
