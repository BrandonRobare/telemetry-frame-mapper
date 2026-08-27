# Troubleshooting

Errors below are quoted as they actually appear. Find yours, apply the fix. Install steps live in [INSTALL.md](INSTALL.md) and [SETUP.md](SETUP.md).

## CLI

**`error: ffmpeg executable not found: ffmpeg. Install ffmpeg or pass --ffmpeg /path/to/ffmpeg.`**
ffmpeg is not on PATH. Install it (see INSTALL.md) or pass the full path: `--ffmpeg C:\ffmpeg\bin\ffmpeg.exe`. Open a fresh terminal after editing PATH.

**`error: exiftool executable not found: exiftool. Install ExifTool or pass --exiftool /path/to/exiftool.`**
Same story for ExifTool: `--exiftool "%LOCALAPPDATA%\Programs\ExifTool\ExifTool.exe"` on a winget install.

**`error: ffmpeg could not extract SRT metadata: …`**
The video has no extractable subtitle/telemetry track. Causes: the video wasn't recorded with video captions enabled (DJI Fly → Camera settings → Video Captions/Subtitles **on**), the file was re-encoded (stripping data streams), or it's not a DJI source. Stream layout also used to matter — versions before 2.0.4 read a hardcoded stream `0:2`, so a file with no audio track (or an extra timecode/data stream) put the subtitle track at a different index and failed here even though the telemetry was present; upgrade if you see this on a file that does have a `Subtitle` stream. Check with `ffmpeg -i flight.mp4` — you should see a `Subtitle` stream. If you have the matching `.srt` from the SD card, pass it with `--srt`.

**`error: Not enough GPS telemetry was found in the SRT data: …`**
The SRT exists but contains fewer than two GPS fixes — usually an indoor/no-lock flight, or a non-GPS DJI caption format. Open the `.srt` in a text editor; the parser expects `GPS(lon, lat, alt)` patterns with optional `H xxx.xm` relative height.

**Frames get coordinates but they're slightly time-shifted / drift along the path.**
The frame rate estimate is off. Pass the rate you actually used at extraction explicitly, e.g. `--frame-rate 2` if you extracted with `-vf fps=2`. Also check the filenames: the frame index is read as the **last** number in each filename — names like `DJI_0081_frame_42.jpg` need that convention to hold.

**Wrong absolute altitude in EXIF (but positions are right).**
`--takeoff-altitude` is meters above sea level of the launch point, not flight height. DJI telemetry height is relative to takeoff; the CLI adds the two.

## Web app

**Import modal: `400 — Folder not found: <path>`**
The import field takes a path **relative to the repo's `imports/` directory** — enter `2026-06-11-site-a`, not `C:\flights\site-a`. Absolute paths and `..` are rejected (path-traversal hardening). Move your folder under `imports/` first.

**Frontend loads but every panel says it can't reach the API.**
The backend isn't running or is on a different port. Start `python -m backend` from the **repo root**; it uses the `deployment` settings in `config.yaml` and starts one API process. The UI expects `http://localhost:8000` by default (override with `VITE_API_URL`). If the frontend is on another origin, add that exact `http://` or `https://` origin to `deployment.cors_origins` and restart.

**Exports / Storage tab shows files somewhere unexpected.**
Run uvicorn from the repo root. Directory settings in `config.yaml` resolve relative to the config file, but the `processed/` static mount resolves from the working directory.

## Reconstruction

**`COLMAP executable not found: colmap. Install COLMAP and ensure it is on PATH …`**
Install COLMAP (INSTALL.md) and restart the backend so the new PATH is picked up. On Windows the official release zip's `bin` folder must be on PATH (e.g. `C:\colmap\bin`).

**Job fails during a COLMAP stage with stage name + stderr in the log.**
Common causes: too few overlapping frames (extract at a higher fps or fly with more overlap), texture-poor scenes (water, uniform fields), or mixed cameras in one session. Try the `quick` preset on a 40–80 frame subset to isolate. Note: in a headless service process COLMAP's SiftGPU may silently fall back to CPU (no OpenGL context) — feature extraction taking minutes per few dozen 4K frames is that, not a hang.

**Status ends `complete` but step says `colmap_only` — no splat in the viewer.**
Training dependencies are missing; the log will show `Gaussian Splatting skipped: …` with guidance ending in "The reconstruction will complete with COLMAP sparse cloud only." Install torch + gsplat per [SETUP.md](SETUP.md). You still have the sparse cloud, LAS export, and coverage data.

**`GPU ran out of memory — switch to 'quick' preset or reduce frame count`**
Exactly that. 4 GB cards: use `quick`, reduce the frame selection in the Review tab, or crop to a target area. Close other GPU apps (browsers with WebGL tabs count).

**First training job sits at the start of `running_gsplat` for many minutes.**
If no prebuilt gsplat wheel matched your torch/CUDA, gsplat JIT-compiles its CUDA kernels on the **first rasterization** (5–15 min; needs MSVC `cl.exe` and `nvcc` on PATH on Windows). Warm up once before starting jobs (see the SETUP.md GPU section).

**Job fails immediately at `running_gsplat` / "loading COLMAP model" with `Command '['where', 'cl']' returned non-zero exit status 1` (Windows).**
COLMAP succeeded but training can't start because `cl.exe` isn't on PATH. torch's CUDA-extension loader re-runs a compiler check on **every** load, even when the kernels are already compiled and cached — so the **backend process itself** must be launched from a VS x64 Developer Command Prompt (`vcvars64`), not just the one-time warm-up. Restart `uvicorn` from that environment. See SETUP.md.

**Mesh export: `SuGaR is not installed. Install optional reconstruction dependencies.`**
SuGaR has no PyPI package; it's a manual install from the [upstream project](https://github.com/Anttwo/SuGaR). Mesh export is optional — everything else works without it.

**Server flythrough: `gsplat video rendering is not installed. Use browser recording or install …`**
The in-browser recorder (WebM via MediaRecorder) is the primary path and needs nothing extra — use it. The server MP4 render requires the full GPU training stack.

**Cancel button seems ignored mid-training.**
Cancellation is polled between steps and between training iterations; allow a few seconds for the job to stop. A cancel during training ends the job as `failed` with "Cancelled by user".

## Splat viewer

**Viewer stuck on loading / "Failed to load splat viewer" with a completed reconstruction.**
1) Confirm the reconstruction actually produced a splat (`exports/{id}/splat.ply` exists; `colmap_only` runs have none). 2) Confirm the build passes an explicit PLY format to the viewer — without it the library mis-detects the format from the `?lod=preview` URL. 3) WebGL2 must be available (check `chrome://gpu`).

**Annotations/measurements disabled, GPS readout missing.**
The reconstruction is not georeferenced: the COLMAP→UTM solve failed, so `geo_transform` is NULL. Three causes, in rough order of likelihood: (1) the flight line is near-collinear — a single straight pass gives the fit no lateral spread to work with, so fly a cross-pass or an offset leg; (2) fewer than three frames carry usable GPS EXIF; (3) the frames span too small an area for a stable fit. Re-import properly geotagged frames from a two-axis flight and reconstruct again. LAS/LAZ exports from a non-georeferenced reconstruction are still valid, but sit in a local frame with no CRS.

## General

**Anything else:** the Jobs tab log panel and the uvicorn console carry stage-specific errors; the API is self-documenting at `http://localhost:8000/docs`. File issues at the GitHub repo with the log excerpt and your OS/GPU details.
