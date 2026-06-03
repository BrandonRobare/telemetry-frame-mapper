# v1.0 external tool and optional reconstruction release gates

## Audit result

| Gate | Current behavior | Test/doc status | v1.0 classification |
|---|---|---|---|
| `ffmpeg` | `extract_srt()` and `read_video_start()` call `ffmpeg` via argv lists, no shell. Missing binary now raises `RuntimeError` with `--ffmpeg` install guidance. Failed extraction returns stderr. | Added missing-binary tests in `tests/cli/test_external_tools.py`; README/CONTRIBUTING document required CLI gate. | Must-pass real CLI smoke for v1.0. |
| `exiftool` | `write_exif()` writes an args file and invokes `exiftool -@ <args_file>` via argv list, no shell. Missing binary now raises `RuntimeError` with `--exiftool` install guidance. Nonzero exits include stdout/stderr. | Added missing-binary test in `tests/cli/test_external_tools.py`; existing GPS tag args test still covers generated tag content. | Must-pass real CLI smoke for v1.0. |
| `COLMAP` | `_run_colmap()` invokes `colmap feature_extractor`, `exhaustive_matcher`, `mapper`, and `model_converter` via argv lists. Missing binary now raises clear install/PATH guidance; nonzero stage exits identify the COLMAP stage and include stderr. | Added missing-binary test in `tests/backend/test_reconstruction_service.py`; docs mark as optional/manual reconstruction gate. | Optional/manual for v1.0 unless reconstruction is promoted to production-ready. |
| `gsplat` / CUDA | `_run_gsplat()` lazy-imports `gsplat.train`; backend import does not require gsplat. Missing training dependency fails the reconstruction job with install guidance. CUDA OOM is mapped to a user-facing preset/frame-count hint. Thumbnail generation degrades silently if `gsplat.render_nadir` is unavailable. The `reconstruction` extra now includes `gsplat>=1.5.0`, making the existing `pip install '.[reconstruction]'` guidance resolvable. | Existing tests cover thumbnail no-gsplat behavior and pipeline happy path; docs mark gsplat/CUDA as optional/manual. | Optional/manual for v1.0. |
| SuGaR | `_run_sugar()` lazy-imports `sugar_scene.export_mesh` or `sugar.export_mesh`; backend import does not require SuGaR. Missing dependency raises `SuGaR is not installed`, and mesh job records failed status/error. `pip index` confirmed no installable `sugar`/`sugar-scene` PyPI package, so the broken `sugar` extra dependency was removed; SuGaR remains a manual upstream install. | Existing tests cover missing SuGaR and mesh job failure propagation; docs mark as optional/manual. | Optional/manual for v1.0. |
| Server-side video render fallback | `_run_video_renderer()` lazy-imports `gsplat`, requires `render_video`, and tells users to use browser recording or install optional reconstruction dependencies when absent. Flythrough job records failed status/error. | Existing tests cover missing gsplat browser fallback and flythrough job success/failure. | Optional/manual for v1.0. |

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
