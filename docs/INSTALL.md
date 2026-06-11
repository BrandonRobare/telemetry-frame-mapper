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

## 5. GPU splat training (optional)

Torch and gsplat are **deliberately not** in the pip extras — CUDA-enabled torch is not on the default PyPI index, and gsplat must compile against your torch/CUDA combination. Follow the step-by-step in [SETUP.md](SETUP.md). Without them, everything still works except splat training itself: reconstructions complete in `colmap_only` mode.

## Uninstall / clean state

All state is local and file-based: delete `data/` (database), `processed/` (thumbnails), `exports/` (outputs), and `imports/` (your images) to reset. `pip uninstall drone-video-geotagger` removes the package.
