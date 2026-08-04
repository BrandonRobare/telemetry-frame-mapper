# Installation

What you need depends on how much of the pipeline you use:

| You want to… | You need |
|---|---|
| Geotag video frames (CLI only) | Python 3.11+, `ffmpeg`, `exiftool` |
| Use the web app (map, review, plan, export) | + Node 20.19+, the `[backend]` Python extra |
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

For a packaged Windows application instead of a developer checkout, see the
[Windows installer workflow](WINDOWS-INSTALLER.md).

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

Requires Node 20.19+ (Vite 8 declares `^20.19.0 || >=22.12.0`). The UI expects the backend at `http://localhost:8000` (override with a `VITE_API_URL` env var).

## 4. Run it

From the **repo root** (paths in `config.yaml` resolve relative to it):

```bash
python -m backend    # one API process: http://localhost:8000, docs: /docs
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

Repeated wrong PINs from the same client are throttled: after 5 consecutive failures each
further attempt is delayed with exponential backoff, and after 10 the client is locked out for
15 minutes. Blocked attempts return `429` with a `Retry-After` header; a correct PIN clears the
counter. The same limiter guards `POST /share/token/{token}/unlock`. Counters live in memory and
reset when the backend restarts.

### One API process only (v2.0.2)

PIN unlock sessions, share-link unlock sessions, and PIN/share throttles are process-local. Run
one API process on one host: do not add Uvicorn/Gunicorn workers or place multiple API containers
or hosts behind a proxy. Multi-process and cross-host API serving are unsupported in v2.0.2; this
limitation does not add cross-process coordination.

### Binding beyond loopback

`deployment.host` defaults to `127.0.0.1`. If you set it to a LAN address or `0.0.0.0` while
neither `pin_lock` nor `api_key` is enabled, the backend refuses to start — an unauthenticated API
on the network would expose every project and file. Enable a PIN lock (or automation key), keep the
loopback bind, or, only if you genuinely intend an open LAN deployment, set
`deployment.allow_unauthenticated_lan: true` to override the guard.

List every browser origin that may call the API in `deployment.cors_origins`. Wildcards are
rejected at startup.

```yaml
deployment:
  host: "192.168.1.50"
  port: 8000
  cors_origins:
    - "http://192.168.1.50:5173"
```

### Host header allowlist

The backend only answers requests addressed to a host it recognises. This blocks DNS rebinding,
where a page on an attacker's domain re-resolves to `127.0.0.1` and becomes same-origin with your
loopback instance — CORS cannot stop that, because the browser considers it the same origin.

The allowlist is derived automatically from `deployment.host`, every hostname in
`cors_origins`, and loopback, which covers every setup above. Set `deployment.allowed_hosts`
explicitly only when you reach the app by an address none of those name — most often a container
published on a LAN IP:

```yaml
deployment:
  allowed_hosts:
    - "192.168.1.50"
    - "mapper.lan"
```

A request with an unlisted `Host` header gets `400 Invalid host header`. Use `["*"]` to disable the
check entirely, which is only reasonable behind a reverse proxy that already validates the host.

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

### Backend logs

The backend writes JSON Lines to `logs/backend.jsonl` by default. The `logging` block in
`config.yaml` sets its level, directory, file name, rotation size, and retention count; set
`enabled: false` to turn it off. The path resolves relative to the config file, and rotation is
handled by Python's standard library — nothing is sent anywhere.

## 5. Optional tools

Everything below is detected at runtime. Missing tools degrade specific features; they never break
startup or the test suite.

| Tool | Needed for | What happens without it |
|---|---|---|
| `colmap` | Reconstruct tab SfM | The job fails with `COLMAP executable not found` and install guidance. |
| `torch` + `gsplat` + CUDA GPU | Splat training, GPU thumbnails, server-side video render | The job completes COLMAP-only; thumbnails degrade quietly; server video rendering tells you to record in the browser instead. Manual two-step install — see [SETUP.md](SETUP.md). |
| SuGaR | Mesh export | Mesh export fails with `SuGaR is not installed`. No pip package exists; install from the upstream project. |
| PotreeConverter | Potree export | Install the [PotreeConverter](https://github.com/potree/PotreeConverter) executable on `PATH`, or point `POTREE_CONVERTER` at it. Download a reconstruction LAS first, then choose **Generate Potree**; the API writes `exports/{id}/potree/metadata.json` and its hierarchy. |

## 6. GPU splat training (optional)

Torch and gsplat are **deliberately not** in the pip extras — CUDA-enabled torch is not on the default PyPI index, and gsplat must compile against your torch/CUDA combination. Follow the step-by-step in [SETUP.md](SETUP.md). Without them, everything still works except splat training itself: reconstructions complete in `colmap_only` mode.

## Uninstall / clean state

All state is local and file-based: delete `data/` (database), `processed/` (thumbnails), `exports/` (outputs), and `imports/` (your images) to reset. `pip uninstall drone-video-geotagger` removes the package.
