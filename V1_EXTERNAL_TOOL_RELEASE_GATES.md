# v1.0 external tool and optional reconstruction release gates

## Audit result

| Gate | Current behavior | Test/doc status | v1.0 classification |
|---|---|---|---|
| `ffmpeg` | `extract_srt()` and `read_video_start()` call `ffmpeg` via argv lists, no shell. Missing binary now raises `RuntimeError` with `--ffmpeg` install guidance. Failed extraction returns stderr. | Added missing-binary tests in `tests/cli/test_external_tools.py`; README/CONTRIBUTING document required CLI gate. | Must-pass real CLI smoke for v1.0. |
| `exiftool` | `write_exif()` writes an args file and invokes `exiftool -@ <args_file>` via argv list, no shell. Missing binary now raises `RuntimeError` with `--exiftool` install guidance. Nonzero exits include stdout/stderr. | Added missing-binary test in `tests/cli/test_external_tools.py`; existing GPS tag args test still covers generated tag content. | Must-pass real CLI smoke for v1.0. |
| `COLMAP` | `_run_colmap()` invokes `colmap feature_extractor`, `exhaustive_matcher`, `mapper`, and `model_converter` via argv lists. Missing binary now raises clear install/PATH guidance; nonzero stage exits identify the COLMAP stage and include stderr. | Added missing-binary test in `tests/backend/test_reconstruction_service.py`; docs mark as optional/manual reconstruction gate. | Optional/manual for v1.0 unless reconstruction is promoted to production-ready. |
| `gsplat` / CUDA | `_run_gsplat()` lazy-imports `gsplat.train`; backend import does not require gsplat. Missing training dependency fails the reconstruction job with install guidance. CUDA OOM is mapped to a user-facing preset/frame-count hint. Thumbnail generation degrades silently if `gsplat.render_nadir` is unavailable. The `reconstruction` extra intentionally does **not** include torch/gsplat (CUDA torch is absent from the default PyPI index and gsplat's sdist needs torch at build time); GPU training install is a manual two-step per docs/SETUP.md. Absence behavior is unchanged. | Existing tests cover thumbnail no-gsplat behavior and pipeline happy path; docs mark gsplat/CUDA as optional/manual. | Optional/manual for v1.0. |
| SuGaR | `_run_sugar()` lazy-imports `sugar_scene.export_mesh` or `sugar.export_mesh`; backend import does not require SuGaR. Missing dependency raises `SuGaR is not installed`, and mesh job records failed status/error. `pip index` confirmed no installable `sugar`/`sugar-scene` PyPI package, so the broken `sugar` extra dependency was removed; SuGaR remains a manual upstream install. | Existing tests cover missing SuGaR and mesh job failure propagation; docs mark as optional/manual. | Optional/manual for v1.0. |
| Server-side video render fallback | `_run_video_renderer()` lazy-imports `gsplat`, requires `render_video`, and tells users to use browser recording or install optional reconstruction dependencies when absent. Flythrough job records failed status/error. | Existing tests cover missing gsplat browser fallback and flythrough job success/failure. | Optional/manual for v1.0. |

## T14 GPU smoke results (2026-06-12)

Machine: RTX 3050 Ti Laptop (4 GB), driver 610.47, CUDA Toolkit 13.2, VS 2022 (MSVC 14.44),
Windows 11. Stack: Python 3.12, torch 2.9.1+cu130, gsplat 1.5.3 (sdist, JIT-compiled —
see docs/SETUP.md for the verified install incl. all workarounds). Dataset: 86 frames
(every 10th of a 854-frame 4K house orbit, no GPS EXIF), quick preset.

| # | Step | Result |
|---|------|--------|
| 1 | torch installed, `torch.cuda.is_available()` | ✅ True (after pinning torch==2.9.1; 2.12 breaks gsplat 1.5.3's JIT call) |
| 2 | gsplat warm-up | ✅ kernels JIT-compiled in 286 s; note: compile triggers on first **rasterization**, not import |
| 3 | Quick reconstruction end-to-end | ✅ `running_colmap` → `running_gsplat` (iteration counts in step labels, e.g. `training 628/1000`) → `complete/done` in **6 min** total; `exports/2/splat.ply` (8.49 MB) + `_preview` (0.85 MB) + `_medium` (4.25 MB); `processed/thumbs/splat_2.jpg` rendered (recognizable nadir aerial scene); DB row: gaussian_count **85 635**, PSNR **23.19**, SSIM **0.589**, training_metrics 4 points (PSNR 21.3→23.2) |
| 4 | Splat Viewer loads the PLY | ✅ after fixing a latent viewer hang (this PR): `SharedArrayBuffer` is unavailable without cross-origin isolation, so `sharedMemoryForWorkers: false` is required; preview LOD renders with sane colors, PSNR/SSIM sparklines render |
| 5 | VRAM watch / max-gaussian cap | ✅ no OOM. Peak 3 918 MiB (COLMAP SiftGPU during feature extraction); training peaked ≈2 119 MiB. Cap (350 k) **not exercised** — quick run densified to 85 635 gaussians; cap freeze remains covered by unit tests only at this scale |
| 6 | Cancel mid-training | ✅ cancelled at iteration 39 → `status=failed`, `error_msg="Cancelled by user"` (pre-T4 this was mislabeled a successful colmap_only completion) |
| 7 | Server flythrough MP4 | ✅ 3 keyframes via viewer UI → h264 1920×1080, 181 frames, 6.03 s, rendered in ~10 s |
| 8 | Full-preset run (rec 6, 2026-06-13/14) | ✅ **complete in 70 min** (COLMAP ~4 min, 30,000 training iters ~66 min). Final **PSNR 27.45 / SSIM 0.794** (vs quick's 23.19 / 0.589); 30 sparkline points (PSNR 22.16→27.45 over training). **gaussian_count 1,015,964 — the 1,000,000 cap fired** (count pins just above the cap; without the densification freeze it would have run away). **Peak VRAM 3,921 MiB, no OOM** on the 4 GB card — peak is COLMAP SiftGPU feature extraction; training itself held ≈2,340 MiB. Artifacts: `splat.ply` 159 MB + `_medium` 79 MB + `_preview` 16 MB + thumbnail |

Step 3 also re-validated along the way: session import progress polling (F5 fix), the
no-GPS ingest path (images flagged `no_gps`, made usable via Review-tab PATCH), and the
`/system/resources` `colmap_available`/`gsplat_available` flags flipping live (T12).

**Critical runtime finding (corrects the earlier overnight guidance):** the backend must
run **inside the VS `vcvars64` environment** (`cl.exe` on PATH) even when gsplat's CUDA
kernels are already compiled and cached. torch's extension loader re-runs a `where cl`
compiler-ABI check on **every** load, so a backend started without `cl.exe` fails the
first training job at "loading COLMAP model" with `Command '['where', 'cl']' returned
non-zero exit status 1` — COLMAP succeeds, only training dies. Two of the three full-run
attempts failed this way (rec 4) or on a dirty reused COLMAP workspace (rec 5, bundle
adjustment); a clean workspace + the vcvars environment produced the clean rec 6 above.
docs/SETUP.md updated accordingly.

## Release decision

Must-pass for v1.0:

1. Python unit tests for CLI parsing, frame interpolation, ExifTool arg generation, fake/missing external tools, and backend graceful-degradation checks.
2. `ruff check .`.
3. Manual real-tool CLI smoke with `ffmpeg` and `exiftool` on at least the primary Linux release environment.

Optional/manual for v1.0:

1. Real COLMAP reconstruction smoke.
2. Real gsplat/CUDA training smoke.
3. Real SuGaR mesh export smoke.
4. Server-side flythrough rendering smoke; browser recording remains the fallback path.

CI should not require real DJI videos, `ffmpeg`, `exiftool`, COLMAP, CUDA, gsplat, or SuGaR. Keep CI on fakes/mocks for absence and clear error messages.
