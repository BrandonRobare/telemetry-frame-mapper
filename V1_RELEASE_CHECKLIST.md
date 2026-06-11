# v1.0 Release Checklist

Master work list for shipping telemetry-frame-mapper 1.0 as a complete **drone video → gaussian splats** pipeline. Produced by the 2026-06-11 release audit (full findings: [docs/release-audit-v1.md](docs/release-audit-v1.md)).

**How to use this file.** Each task below is self-contained: it carries its own context, file anchors, steps, acceptance criteria, and verification commands, so it can be handed to an agent with no other briefing. Line numbers were verified against commit `80c90e8` (2026-06-11); they drift, so every anchor has a grep fallback. Work each task on its own branch, open a PR to `main`, and check the box only when the PR is merged with CI green.

**Project conventions (apply to every task):**
- Python 3.10+, `from __future__ import annotations` at the top of every module, `Path` objects (not strings) in public interfaces.
- `ruff check .` must pass (rules E, F, I, UP, B; line length 100).
- Tests use inline fixture data — never real flight files. CI has no GPU, no ffmpeg/exiftool/COLMAP, no torch: external tools and optional heavy deps are mocked per [V1_EXTERNAL_TOOL_RELEASE_GATES.md](V1_EXTERNAL_TOOL_RELEASE_GATES.md).
- Run `pytest` and `ruff check .` before declaring any task done. Frontend tasks: `cd frontend && npm run lint && npm test -- --run && npm run build`.

**Dependency order:**

```
T1 (colmap_io)  ──┐
T2 (ply_io)     ──┼──> T3 (trainer) ──> T4 (wiring) ──> T5 (viewer fix) ──> T14 (GPU smoke)
                  │
T6 T7 T8 T9 T10 T11 T12 T13   (independent, any order, parallelizable)
                  │
all of the above ──> T15 (tag & release)
```

T1 and T2 are independent of each other and ideal first parallel dispatches.

**Status legend:** `[ ]` open · `[x]` merged to main.

---

## P0 — Release blockers

### T1 — [ ] New module `backend/services/colmap_io.py`: COLMAP sparse-model loader

**Goal:** A pure-numpy loader for COLMAP sparse models so the splat trainer (T3) can read camera poses and points without any COLMAP Python bindings.

**Context.** `_run_colmap()` in [backend/services/reconstruction.py](backend/services/reconstruction.py) (grep `def _run_colmap`) runs `feature_extractor → exhaustive_matcher → mapper → model_converter`. The mapper writes a **BIN** model to `colmap_dir/sparse/0/`; `model_converter` then converts in place to TXT with the same output path, so `sparse/0/` ends up containing **both** `cameras.bin/images.bin/points3D.bin` and the `.txt` variants. Source frames are in `colmap_dir/images/`. The workspace uses a single PINHOLE camera. `image_undistorter` is not run (PINHOLE has zero distortion, so that is fine).

**Create:**
- `backend/services/colmap_io.py` (~300 lines) — stdlib + numpy only. No torch, no gsplat, no backend imports.
- `tests/backend/test_colmap_io.py`

**API:**
```python
@dataclass(frozen=True)
class ColmapCamera:
    camera_id: int; model: str; width: int; height: int
    params: np.ndarray              # PINHOLE: fx fy cx cy

@dataclass(frozen=True)
class ColmapImage:
    image_id: int
    qvec: np.ndarray                # wxyz quaternion, world->cam rotation
    tvec: np.ndarray
    camera_id: int
    name: str

@dataclass(frozen=True)
class ColmapModel:
    cameras: dict[int, ColmapCamera]
    images: list[ColmapImage]
    points_xyz: np.ndarray          # (P, 3) float64
    points_rgb: np.ndarray          # (P, 3) uint8

def read_model(sparse_dir: Path) -> ColmapModel      # prefers .bin, falls back to .txt
def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray
def world_to_cam_matrix(image: ColmapImage) -> np.ndarray   # 4x4 viewmat
```

**Implementation notes:**
- BIN format per COLMAP's documented binary layout (`struct.unpack` / `np.frombuffer`): `cameras.bin` = `<Q` count, then per camera `<iiQQ` + `<d` × num_params (param count derived from model id; support PINHOLE=1 and SIMPLE_PINHOLE=0, raise `RuntimeError` naming the model for anything else). `images.bin` = per image header `<idddddddi`, then a null-terminated name, then `<Q` num_points2D — skip `24 * num_points2D` bytes. `points3D.bin` = `<Q` count, per point `<Q ddd BBB d Q`, then skip `8 * track_len` bytes.
- TXT parsing mirrors the line conventions already used by `_read_colmap_points3d` and `_store_reprojection_errors` in reconstruction.py (2 lines per image; skip `#` comments).
- `read_model` raises `RuntimeError(f"COLMAP sparse model not found in {sparse_dir}")` if neither format exists.

**Tests** (fixtures built in-test with `struct.pack` — no binary files committed):
`test_read_cameras_bin_pinhole`, `test_read_images_bin_quaternion_and_name`, `test_read_points3d_bin_xyz_rgb_skips_track`, `test_read_model_prefers_bin_over_txt`, `test_read_model_txt_fallback_matches_bin`, `test_read_model_missing_raises_runtime_error`, `test_unsupported_camera_model_raises`, `test_qvec_to_rotmat_identity_and_known_rotation`.

**Acceptance:** all new tests pass in CI (no GPU, no torch); `ruff check .` clean; module imports with only numpy installed.

---

### T2 — [ ] New module `backend/services/ply_io.py`: 3DGS PLY read/write/prune

**Goal:** Read and write Gaussian-splat PLY files in the standard INRIA 3DGS layout — the exact format `@mkkellogg/gaussian-splats-3d` (the frontend viewer) consumes — plus a numpy-only opacity prune for LOD generation.

**Context.** Today `_generate_lod` (reconstruction.py, grep `def _generate_lod`) calls a nonexistent `gsplat.prune_by_opacity` and silently does nothing. The viewer, the LAS export (`_load_ply_positions_and_colors`), and coverage gaps (`_compute_coverage_gaps`) all read the splat PLY, so the layout written here is a hard compatibility contract.

**Create:**
- `backend/services/ply_io.py` (~220 lines) — stdlib + numpy only.
- `tests/backend/test_ply_io.py`

**API:**
```python
@dataclass
class GaussianCloud:
    means: np.ndarray       # (N,3) f32
    sh0: np.ndarray         # (N,3) f32          -> f_dc_0..2
    shN: np.ndarray         # (N,K,3) f32, K may be 0 -> f_rest_*
    opacities: np.ndarray   # (N,) f32, raw logits
    scales: np.ndarray      # (N,3) f32, log-space
    quats: np.ndarray       # (N,4) f32, wxyz

def write_3dgs_ply(path: Path, cloud: GaussianCloud) -> Path
def read_3dgs_ply(path: Path) -> GaussianCloud
def prune_by_opacity(src: Path, dst: Path, keep_ratio: float) -> Path
def ply_property_names(sh_degree: int) -> list[str]
```

**Hard requirements (each gets a test):**
1. Header: `format binary_little_endian 1.0`, one `element vertex N`, all `property float`, in **exactly** this order: `x y z nx ny nz f_dc_0 f_dc_1 f_dc_2 f_rest_0 .. f_rest_{3K-1} opacity scale_0 scale_1 scale_2 rot_0 rot_1 rot_2 rot_3`. Write `nx ny nz` as zeros (INRIA includes them; the viewer ignores them but third-party tools expect them).
2. **f_rest is channel-major** (INRIA convention): transpose `(N, K, 3)` → `(N, 3, K)` before flattening — all R coefficients, then G, then B. Getting this wrong silently corrupts view-dependent color in the viewer.
3. `rot_0..3` is quaternion **w,x,y,z** (gsplat's native order). Opacity and scales are exported as raw logit/log values — the viewer applies sigmoid/exp itself.
4. Write via a structured `np.dtype([... "<f4" ...])` and a single `tobytes()`; read via the inverse. Tolerate `\r\n` in the header (see the header scan in `_load_ply_positions_and_colors` for the existing approach).
5. `prune_by_opacity`: sort by opacity descending (raw logits — sigmoid is monotonic, no activation needed), keep `max(1, int(N * keep_ratio))` rows, write to `dst`.

**Tests:** `test_write_read_roundtrip_preserves_all_attributes` (sh degree 0 and 2), `test_header_property_order_matches_inria_layout` (assert exact `ply_property_names(2)` sequence), `test_f_rest_is_channel_major` (known shN, assert byte layout), `test_prune_by_opacity_keeps_top_fraction`, `test_prune_keeps_at_least_one`, `test_written_ply_readable_by_existing_loader` (feed output to `_load_ply_positions_and_colors` and `_compute_coverage_gaps` from reconstruction.py — proves the LAS-export and coverage-gap paths keep working).

**Acceptance:** tests pass in CI; `ruff` clean; no torch/gsplat imports anywhere in the module.

---

### T3 — [ ] New module `backend/services/splat_trainer.py`: real gaussian-splat training

**Goal:** Replace the phantom `gsplat.train` API with a real training loop built on `gsplat.rasterization` so reconstructions actually produce a splat. **This is the 1.0 headline feature** — without it the product never produces a gaussian splat (see audit finding F11-bis in [docs/release-audit-v1.md](docs/release-audit-v1.md)).

**Depends on:** T1, T2.

**Context — contracts the trainer must honor** (all in [backend/services/reconstruction.py](backend/services/reconstruction.py)):
- `_run_gsplat(colmap_dir, output_path, iterations, progress_cb, cancel)` (grep `def _run_gsplat`) must return `{gaussian_count, psnr, ssim, training_metrics}`. `training_metrics` is `list[{iter: int, psnr: float, ssim: float}] | None` — stored as JSON on `Reconstruction.training_metrics` and rendered as sparklines by `TrainingMetricsPanel` in `frontend/src/features/splat/SplatViewerTab.tsx`.
- `progress_cb(step: str, pct: float)` — **each call is a DB UPDATE + commit**. Throttle to at most one call per 2 seconds (wall clock). Map progress into the 95.0 → 99.5 window (COLMAP owns 0–95; no frontend change needed).
- `cancel: threading.Event` — poll every iteration; raise `ReconstructionCancelled` (define it in this module as a `RuntimeError` subclass) when set.
- Missing torch/gsplat must raise `RuntimeError` whose message contains **"COLMAP sparse cloud only"** — the pipeline's except-branch (grep `colmap_only`) keys off generic RuntimeError to complete gracefully, and the existing tests assert that wording family.
- CUDA OOM must surface as `RuntimeError` containing the literal substring **"CUDA out of memory"** — the pipeline (grep `CUDA out of memory`) maps it to a user-facing preset hint.
- The real gsplat (>=1.5) exports `rasterization` and densification strategies (`DefaultStrategy`); the training loop is user-written. Reference: gsplat's `examples/simple_trainer.py`.

**Create:**
- `backend/services/splat_trainer.py` (~550 lines). Module top imports: stdlib, numpy, `colmap_io`, `ply_io` only. `torch`, `gsplat`, `PIL` are imported **inside functions** so the backend never requires them.
- `tests/backend/test_splat_trainer.py`

**API:**
```python
class ReconstructionCancelled(RuntimeError): ...

_GPU_LOCK = threading.Lock()    # one GPU job at a time (target card: 4 GB)

@dataclass
class TrainerConfig:
    iterations: int
    sh_degree: int
    downscale_factor: int
    max_gaussians: int
    refine_start_iter: int
    refine_stop_iter: int
    refine_every: int = 100
    reset_every: int = 3000
    eval_every: int = 1000
    eval_views: int = 4
    ssim_lambda: float = 0.2
    init_opacity: float = 0.1

    @classmethod
    def from_preset(cls, preset_cfg: dict) -> TrainerConfig: ...

def train_splats(colmap_dir: Path, output_path: Path, config: TrainerConfig,
                 progress_cb, cancel: threading.Event) -> dict
def render_thumbnail(splat_path: Path, out_path: Path,
                     width: int = 512, height: int = 512) -> Path | None
def render_flythrough(splat_path: Path, output_path: Path, keyframes: list[dict],
                      *, fps: int, width: int, height: int) -> Path
```

**Preset hyperparameters** (defaults in code; optional per-preset overrides read from `config.yaml → reconstruction.presets.*` by `from_preset` — presets currently carry only `iterations`, see `get_reconstruction_config` in [backend/core/config.py](backend/core/config.py), grep `def get_reconstruction_config`):

| Parameter | quick (1000 it) | full (30000 it) | Why |
|---|---|---|---|
| downscale_factor | 4 (→1000×750) | 2 (→2000×1500) | 4000×3000 sources must fit 4 GB VRAM |
| sh_degree | 1 | 2 | the viewer renders ≤ degree 2; degree 3 wastes memory |
| max_gaussians | 350 000 | 1 000 000 | ≈0.46 GB params+Adam at 1M/deg-2 |
| refine start/stop/every | 300 / 800 / 100 | 500 / 15000 / 100 | standard 3DGS; quick barely densifies by design |
| reset_every | disabled (> iterations) | 3000 | opacity reset destabilizes ultra-short runs |
| eval_every / eval_views | 250 / 4 | 1000 / 4 | ~30 sparkline points on full |
| loss | 0.8·L1 + 0.2·(1−SSIM) | same | INRIA default |
| lr: means | 1.6e-4·scene_scale, exp decay ×0.01 over run | same | simple_trainer defaults |
| lr: scales/quats/opacities/sh0/shN | 5e-3 / 1e-3 / 5e-2 / 2.5e-3 / 1.25e-4 | same | |
| sh warmup | +1 degree per 500 it | +1 per 1000 it | standard |
| init opacity / scale | 0.1 / log(mean 3-NN dist) | same | |
| rasterization | packed=True, fp32, batch 1 | same | packed saves memory on sparse aerial scenes |

**Training loop sketch:**
1. `model = colmap_io.read_model(colmap_dir / "sparse" / "0")`. Dataset: for each registered image load `colmap_dir/images/{name}` with PIL, LANCZOS-downscale by `downscale_factor`, cache as **uint8 CPU tensors** (never float32 — 500 frames at 1000×750 ≈ 1.1 GB RAM). Scale fx/fy/cx/cy by the same factor. Per iteration: one random view, `to(device).float()/255`.
2. Init params from sparse points: `means = points_xyz`; `sh0 = (rgb/255 − 0.5) / 0.2820947918`; `shN = zeros(N, K, 3)`, `K = (sh_degree+1)² − 1`; `scales = log(mean dist to 3 nearest neighbors)` (chunked `torch.cdist`, 4096-point blocks); `quats = (1,0,0,0)`; `opacities = logit(init_opacity)`. `scene_scale = 1.1 × max camera distance from camera-center centroid`.
3. Per-attribute `torch.optim.Adam` with the lr table above; means lr on `ExponentialLR` (gamma `0.01**(1/iterations)`).
4. `strategy = gsplat.DefaultStrategy(refine_start_iter=…, refine_stop_iter=…, refine_every=…, reset_every=…, verbose=False)`; `strategy.check_sanity(...)`; `state = strategy.initialize_state(scene_scale=scene_scale)`.
5. Each iteration: check cancel → `ReconstructionCancelled`; render via `gsplat.rasterization(means, quats, exp(scales), sigmoid(opacities), colors=cat(sh0, shN), viewmats, Ks, W, H, sh_degree=min(step // warmup, sh_degree), packed=True)`; loss = `(1−λ)·L1 + λ·(1−SSIM)` (SSIM: pure-torch 11×11 gaussian-window implementation, ~30 lines — do not add torchmetrics); `strategy.step_pre_backward`; backward; `strategy.step_post_backward(..., packed=True)`; optimizer steps; scheduler step.
6. **VRAM cap:** after `step_post_backward`, if `len(means) >= config.max_gaussians`, set `strategy.refine_stop_iter = step` (freezes densification) and report once via `progress_cb`.
7. **Eval:** every `eval_every` iterations and at the final step, render `eval_views` evenly spaced training views under `no_grad`, compute PSNR (`−10·log10(mse)`) + SSIM, append `{"iter": step, "psnr": …, "ssim": …}`. Final pair becomes top-level `psnr`/`ssim`. (Train-view metrics — say so in the docstring; a holdout would cost quality at drone-survey frame counts.)
8. Export with `ply_io.write_3dgs_ply`; return the result dict. Wrap the whole body in `with _GPU_LOCK:` and `try/finally: torch.cuda.empty_cache()`. Re-wrap `torch.cuda.OutOfMemoryError` as `RuntimeError(f"CUDA out of memory: {exc}")`.

**`render_thumbnail`:** return `None` (never raise) when torch/gsplat are unavailable or `_GPU_LOCK.acquire(timeout=0)` fails (best-effort). Load the PLY via `ply_io`; bounds from the 5th–95th percentile of means; ground normal from PCA (smallest-eigenvalue eigenvector, sign toward world −Y to match the viewer's `cameraUp [0,-1,0]`); camera at centroid − normal × (1.4 × max planar extent / (2·tan(30°))); one rasterization call at 512×512, sh_degree 0; clamp → uint8 → JPEG quality 85.

**`render_flythrough`:** `shutil.which("ffmpeg")` missing → `RuntimeError` with install guidance that also mentions browser recording. torch/gsplat missing → keep the exact tested message family "Use browser recording or install optional reconstruction dependencies." Interpolate keyframe position/target with smoothstep `t·t·(3−2t)` (matches the frontend preview — grep `smoothstep\|3 - 2 \*` in SplatViewerTab.tsx); look-at viewmats with up = world −Y; render per frame under `no_grad`; pipe raw RGB to `ffmpeg -y -f rawvideo -pix_fmt rgb24 -s {w}x{h} -r {fps} -i - -c:v libx264 -pix_fmt yuv420p -movflags +faststart {out}` via stdin. Cap resolution at 1920×1080 server-side.

**Tests (CI, no GPU/torch):** `test_module_imports_without_torch`, `test_train_splats_without_torch_raises_colmap_only_guidance` (assert "COLMAP sparse cloud only" in message), `test_render_thumbnail_without_torch_returns_none`, `test_render_flythrough_without_torch_mentions_browser_recording`, `test_render_flythrough_without_ffmpeg_raises_install_guidance` (fake torch/gsplat modules via `patch.dict(sys.modules, ...)`, `shutil.which` → None), `test_trainer_config_from_preset_quick_and_full_defaults`, `test_smoothstep_keyframe_interpolation_endpoints`.

**Acceptance:** tests pass in CI; `pip install .[backend]` followed by `python -c "import backend.main"` works in an env **without** torch; `ruff` clean.

---

### T4 — [ ] Wire the trainer into `backend/services/reconstruction.py`

**Goal:** Replace every phantom-gsplat call site with the real implementations from T1–T3, preserving the graceful-degradation contracts.

**Depends on:** T1, T2, T3.

**Edits** (anchors at commit `80c90e8`; grep fallbacks given):
1. **`_run_gsplat`** (lines 346–373, grep `def _run_gsplat`): change signature to accept the full `preset_cfg: dict` (not just `iterations`); body becomes `TrainerConfig.from_preset(preset_cfg)` + `return splat_trainer.train_splats(...)`. Delete the `redirect_stdout` block. Keep `_parse_checkpoint_metrics` (grep `_CHECKPOINT_RE`) — tests reference it; add a comment that it is retained for log-replay compatibility.
2. **`_generate_lod`** (lines 376–386, grep `def _generate_lod`): two `ply_io.prune_by_opacity(splat_path, preview, 0.10)` / `(…, medium, 0.50)` calls. No try/except, no gsplat.
3. **`_generate_thumbnail`** (lines 389–399, grep `def _generate_thumbnail`): delegate to `splat_trainer.render_thumbnail(splat_path, out_path)`; keep the `out_path.parent.mkdir(...)` here too (the test `test_generate_thumbnail_creates_parent_dir` expects it).
4. **`_run_video_renderer`** (grep `def _run_video_renderer`, ~line 823): delegate to `splat_trainer.render_flythrough(...)`; keep the output-file existence check and the "Use browser recording" message contract.
5. **`_run_pipeline` caller** (lines 1311–1314, grep `result = _run_gsplat`): pass `preset_cfg`. Insert `except ReconstructionCancelled:` → `status="failed", error_msg="Cancelled by user"` **before** the existing `except RuntimeError` branch (today a mid-training cancel would be mislabeled as a successful colmap_only completion). Keep the colmap_only fallback (lines 1353–1362) byte-for-byte in behavior.
6. Module imports: `from backend.services import ply_io, splat_trainer` + the two trainer symbols at top — all are import-safe without torch.

**Test updates in `tests/backend/test_reconstruction_service.py`:**
- Rewrite the three thumbnail tests (lines 335–380, grep `Thumbnail generation tests`) to patch `splat_trainer.render_thumbnail` instead of `sys.modules["gsplat"]`.
- Add: `test_run_pipeline_gsplat_missing_completes_colmap_only` (patch `_run_gsplat` to raise the guidance RuntimeError; assert status complete + step colmap_only), `test_run_pipeline_cancel_during_training_marks_failed`, `test_run_pipeline_oom_maps_to_preset_hint`, and a mocked-trainer orchestration test: patch `splat_trainer.train_splats` to write a tiny real PLY via `ply_io` and return a full result dict; assert the DB row gets `gaussian_count/psnr/ssim/training_metrics` and that the **real** `_generate_lod` produced loadable preview/medium files.
- `test_run_video_renderer_missing_dependency_reports_browser_fallback` must keep passing unchanged.

**Acceptance:** full `pytest` green in CI (no torch); `ruff` clean; `grep -rn "from gsplat import\|gsplat\.render_nadir\|gsplat\.render_video\|prune_by_opacity" backend/services/reconstruction.py` returns nothing.

---

### T5 — [ ] Frontend: explicit PLY format in the splat viewer

**Goal:** One-line latent-bug fix that blocks T14. The viewer URL ends in `?lod=preview`, and `@mkkellogg/gaussian-splats-3d` infers scene format from the URL suffix — it will misdetect the real PLY the moment T1–T4 produce one (never exercised before because no splat was ever created).

**Depends on:** nothing (can merge before T4); verified live by T14.

**Edit:** `frontend/src/features/splat/SplatViewerTab.tsx` lines 770–782 (grep `addSplatScene`):
```ts
const { Viewer, SceneFormat } = await import('@mkkellogg/gaussian-splats-3d')
...
await viewer.addSplatScene(splatUrl, { streamView: true, format: SceneFormat.Ply })
```

**Acceptance:** `cd frontend && npm run lint && npm run build` clean. (Live load verified in T14 step 4.)

---

### T6 — [ ] Packaging: version 1.0.0 + reconstruction-extra honesty + GPU install docs

**Goal:** Make the package metadata say 1.0, and make the documented install path for GPU training actually resolvable.

**Context.** `pip install ".[reconstruction]"` can never work as advertised: CUDA-enabled torch is not on the default PyPI index, and gsplat's sdist requires torch at build time. The extra currently pins `gsplat>=1.5.0` ([pyproject.toml:55-58](pyproject.toml)).

**Edits:**
1. [pyproject.toml:7](pyproject.toml) `version = "0.1.0"` → `"1.0.0"`; line 17 classifier `3 - Alpha` → `5 - Production/Stable`.
2. Other version strings (all verified present): [backend/main.py:36](backend/main.py) `version="0.1.0"`, [src/drone_video_geotagger/__init__.py:3](src/drone_video_geotagger/__init__.py) `__version__ = "0.1.0"`, [frontend/package.json:4](frontend/package.json) `"version": "0.0.0"` → all `1.0.0`. Then `grep -rn "0\.1\.0" --include="*.py" --include="*.toml" --include="*.json"` (excluding lockfiles/node_modules) and triage any leftover hit.
3. `[project.optional-dependencies] reconstruction`: drop `gsplat>=1.5.0`, keep `laspy>=2.5`, add a TOML comment: torch+gsplat are intentionally not listed (CUDA torch unavailable on default PyPI; gsplat sdist needs torch at build time) — see docs/SETUP.md.
4. `docs/SETUP.md`: replace the gsplat bullet (grep `gsplat`) with a "GPU splat training (Windows)" section: prerequisites (NVIDIA driver, CUDA Toolkit 13.x, MSVC Build Tools C++ workload); two-step install — `pip install torch --index-url https://download.pytorch.org/whl/cu130` then `pip install gsplat --index-url https://docs.gsplat.studio/whl/pt29cu130 --extra-index-url https://pypi.org/simple` — then `pip install -e ".[backend,reconstruction]"`. Notes: if no prebuilt gsplat wheel matches, gsplat JIT-compiles CUDA kernels on **first import** (5–15 min, needs `cl.exe` + `nvcc` on PATH; set `TORCH_CUDA_ARCH_LIST=8.6` for the RTX 3050 Ti); warm up with `python -c "import gsplat"` before the first training job. Torch/nvcc CUDA major versions must match (toolkit 13.2 → cu130 wheels, not cu12x).
5. Update the gsplat row in [V1_EXTERNAL_TOOL_RELEASE_GATES.md](V1_EXTERNAL_TOOL_RELEASE_GATES.md) (the extra no longer includes gsplat; install is manual two-step; absence behavior unchanged) and the matching row in README's external-tools table.

**Acceptance:** `pip install -e ".[backend,dev]"` then `pytest` green; `python -c "import drone_video_geotagger; print(drone_video_geotagger.__version__)"` prints `1.0.0`; started backend's `/openapi.json` reports `1.0.0`.

---

### T7 — [ ] Drop Docker for 1.0

**Goal:** Stop advertising a broken install path. `docker-compose.yml` references `backend/Dockerfile` and `frontend/Dockerfile`; **neither file exists**. Decision (2026-06-11): native install only for 1.0; Docker may return in 1.1 done properly.

**Edits:**
1. `git rm docker-compose.yml`.
2. `docs/SETUP.md`: remove the "GPU Acceleration" docker-compose section (nvidia-container-toolkit + `docker compose --profile nvidia up`, lines 3–30) — T6's new GPU section replaces it.
3. Sweep: `grep -rin "docker" --include="*.md" --include="*.yml" --include="*.yaml" .` (skip node_modules/.git/.internal) and remove or rewrite every remaining reference (README, CONTRIBUTING, tests that read docker-compose.yml — the audit found docker-compose tests in the suite, grep `docker` under `tests/`; delete them with the file).

**Acceptance:** the sweep grep returns no tracked-file hits; `pytest` green (docker tests removed, count drops accordingly — update the count anywhere docs state it).

---

### T8 — [ ] Replace deprecated `datetime.utcnow()` (11 sites)

**Goal:** Eliminate all 174 deprecation warnings (Python 3.12+) before they become errors in future Python versions.

**Edits** (verified line numbers):
- [backend/db/models.py](backend/db/models.py) lines 17, 92, 117, 137, 157, 166, 203, 235, 255: `Column(DateTime, default=datetime.utcnow)` → `Column(DateTime, default=lambda: datetime.now(timezone.utc))` (import `timezone`). Note: these columns are naive-datetime; the lambda returns aware. SQLite stores both fine, but verify the API serialization is unchanged by running the router test suites — if aware datetimes change response shapes (trailing `+00:00`), strip tzinfo in the lambda instead: `lambda: datetime.now(timezone.utc).replace(tzinfo=None)` (preserves current wire format exactly — prefer this if any router test breaks).
- [backend/routers/sessions.py:81](backend/routers/sessions.py): `datetime.datetime.utcnow()` → `datetime.datetime.now(datetime.timezone.utc)` (module imports `datetime` the module — match its style; apply the same naive-vs-aware decision as above).
- [tests/backend/test_comparisons_router.py:53](tests/backend/test_comparisons_router.py): same replacement.

**Acceptance:** `pytest -W error::DeprecationWarning -k "not slow" 2>&1 | grep -c utcnow` → 0; full `pytest` green with **zero** `utcnow` warnings in the summary; `grep -rn "utcnow" backend/ tests/` → empty.

---

## P1 — Quality gates

### T9 — [ ] CI hardening: Python matrix + frontend job

**Goal:** CI currently tests only Python 3.12 and never touches the frontend ([.github/workflows/ci.yml](.github/workflows/ci.yml), 29 lines). The package claims 3.10–3.12 support; the frontend has lint/test/build scripts that never run.

**Edits to `.github/workflows/ci.yml`:**
1. `test` job: `strategy.matrix.python-version: ["3.10", "3.11", "3.12"]`, use `${{ matrix.python-version }}`.
2. New `frontend` job (ubuntu-latest): checkout → `actions/setup-node@v4` with `node-version: 20` and `cache: npm`, `cache-dependency-path: frontend/package-lock.json` → `cd frontend && npm ci && npm run lint && npm test -- --run && npm run build`.
3. Keep the policy from [V1_EXTERNAL_TOOL_RELEASE_GATES.md](V1_EXTERNAL_TOOL_RELEASE_GATES.md): no real ffmpeg/exiftool/COLMAP/CUDA in CI.

**Acceptance:** all four CI jobs green on the PR. Note: `npm test -- --run` currently runs only 2 test files — fine; T10 expands them. If `npm run lint` surfaces pre-existing errors, fix trivial ones in this PR and file the rest as issues rather than relaxing rules.

---

### T10 — [ ] Frontend smoke tests (vitest)

**Goal:** The frontend has 40 source files and 2 test files (`useViewerCoords.test.ts`, `formatDiff.test.ts`). Add ~6–8 high-value pure-logic tests — not full component coverage.

**Targets** (extract logic into testable helpers where needed, keeping behavior identical):
1. `frontend/src/shared/api/mutations.ts` lines 73–76: the import-progress `refetchInterval` — returns 1000 for `pending`/`running`/undefined, `false` only for `done`/`error`. This logic regressed once already (walkthrough finding F5); pin it with a test.
2. `SessionLogTab.tsx` timestamp rendering (grep `toLocaleString`): null timestamp → `"—"`, valid ISO string → no "Invalid Date" (regression test for walkthrough F6).
3. `ImportModal.tsx` path field expectations (relative-to-imports rule, regression for F4) — test whatever validation/helper exists; if validation is inline JSX only, extract a `validateImportPath()` helper first.
4. Smoothstep keyframe interpolation in `SplatViewerTab.tsx` (grep `3 - 2 *`): endpoints and midpoint — must mirror the server-side formula in T3 (cross-implementation contract).
5. 1–2 more at the implementer's discretion (e.g. `formatBytes`/storage-percent helpers in `StorageTab.tsx`).

**Acceptance:** `cd frontend && npm test -- --run` ≥ 8 passing test files/cases total, lint + build clean; no snapshot tests (brittle); no component-render tests requiring jsdom unless trivial.

---

### T11 — [ ] CLI edge-case tests + frame-index regex fix

**Goal:** Close the small CLI gaps the audit found in `src/drone_video_geotagger/`.

1. **Untested fallback:** [frames.py:36-38](src/drone_video_geotagger/frames.py) `infer_frame_rate` returns 8.0 when `telemetry_end_s <= 0`. Add `test_infer_frame_rate_returns_default_without_telemetry` to `tests/cli/test_frames.py`.
2. **Frame-index regex footgun:** [frames.py:28](src/drone_video_geotagger/frames.py) `re.search(r"(\d+)", path.stem)` takes the **first** digit group — `DJI_0081_frame_42.jpg` yields index 81, not 42, silently mis-timing every frame. Fix: use the **last** digit group (`re.findall(r"\d+", path.stem)[-1]`), which is correct for both `frame_00042.jpg` and `DJI_0081_frame_42.jpg`. Add tests for both naming patterns plus a no-digits filename (skipped). Document the rule in the README CLI section ("frame index = last number in the filename").
3. **Defensive timecode parsing:** [telemetry.py:17-25](src/drone_video_geotagger/telemetry.py) `parse_srt_time` is regex-guarded inside `parse_srt_text` but is public API; malformed input currently fails with a bare unpacking ValueError. Wrap with a try/except that re-raises `ValueError(f"Unrecognized SRT timecode: {value!r}")`. Add a test.
4. Confirm the existing `len(points) < 2` guard message (telemetry.py:60-61) is covered by a test; add one if not.

**Acceptance:** new tests pass; full `pytest` green; `ruff` clean; README updated for the frame-index rule.

---

### T12 — [ ] Backend startup preflight for COLMAP

**Goal:** Today a missing COLMAP binary surfaces only when a reconstruction job fails minutes into a session. Warn at startup and expose it to the UI.

**Edits:**
1. [backend/main.py:30-33](backend/main.py) lifespan: after `init_db()`, `shutil.which("colmap")` — if None, `logging.getLogger("backend").warning("COLMAP not found on PATH — reconstruction jobs will fail until it is installed (see docs/INSTALL.md)")`. Never fatal.
2. [backend/routers/system.py](backend/routers/system.py): add `"colmap_available": shutil.which("colmap") is not None` (and `"gsplat_available"`: `importlib.util.find_spec("gsplat") is not None` — spec lookup only, **never import** gsplat here, since import can trigger a multi-minute CUDA JIT compile) to the `/system/resources` response.
3. Frontend (optional, small): `JobsTab.tsx` resource bar shows a warning chip when `colmap_available === false`.
4. Tests: monkeypatch `shutil.which` in a new `tests/backend/test_system_router.py` case asserting both flags appear; lifespan warning test optional.

**Acceptance:** `pytest` green; with COLMAP absent from PATH, backend starts cleanly and logs the warning once; `/system/resources` reports the two new booleans.

---

### T13 — [ ] Fix broken dev scripts (dev.sh / dev.bat)

**Goal:** Both scripts run `cd backend && pip install -r requirements.txt` — but `backend/requirements.txt` was **deleted** by ADR-011 (deps moved to pyproject extras), so both scripts fail on a fresh clone. They also create a venv inside `backend/` and run `uvicorn main:app` from there, which breaks the `backend.main:app` import convention.

**Edits:** in [dev.sh](dev.sh) and [dev.bat](dev.bat): create/use a repo-root `.venv`; install with `python -m pip install -e ".[backend,dev]"`; launch `uvicorn backend.main:app --reload --port 8000` **from the repo root** (config.yaml and `./processed` static mount resolve relative to the root); keep the frontend half (`cd frontend && npm install && npm run dev`) as is. Add a basic `node`/`npm` existence check with a friendly message in dev.bat.

**Acceptance:** on a tree without `backend/.venv`, `./dev.sh` (Git Bash) and `dev.bat` (cmd) both bring up backend on :8000 (`curl -fsS http://localhost:8000/health` → `{"status":"ok"}`) and frontend on :5173.

---

## P2 — Release mechanics

### T14 — [ ] Manual GPU smoke (human-in-the-loop; the one task agents cannot finish alone)

**Goal:** Prove the T1–T6 trainer end-to-end on the real RTX 3050 Ti before tagging. Record results in [V1_EXTERNAL_TOOL_RELEASE_GATES.md](V1_EXTERNAL_TOOL_RELEASE_GATES.md).

**Depends on:** T1–T6 merged. Machine facts: RTX 3050 Ti 4 GB, CUDA Toolkit 13.2, VS build tools present; COLMAP at `C:\colmap\bin\colmap.exe`; exiftool via winget; ffmpeg at `C:\ffmpeg\bin`.

**Procedure:**
1. Install per the new docs/SETUP.md GPU section; `python -c "import torch; print(torch.cuda.is_available())"` → `True`.
2. Warm-up `python -c "import gsplat"` (first run may JIT-compile 5–15 min; watch for cl.exe/nvcc errors).
3. Ingest a short DJI clip (~60–150 frames) and start a **quick** reconstruction. Confirm: status walks `running_colmap → running_gsplat`; progress advances past 95% with iteration counts in `/reconstruction/{id}/log`; `exports/{id}/splat.ply` + `_preview.ply` + `_medium.ply` exist; `processed/thumbs/splat_{id}.jpg` exists; the DB row has gaussian_count/psnr/ssim/training_metrics.
4. Splat Viewer tab: the PLY loads (T5 fix), colors sane, PSNR/SSIM sparklines render.
5. Watch VRAM (`nvidia-smi` or Task Manager); confirm the max-gaussian cap log line appears before any OOM.
6. Cancel a training mid-run → status `failed`, error "Cancelled by user".
7. Add 2 keyframes in the viewer, request the server MP4 → flythrough downloads and plays.
8. Overnight **full** preset run; record peak VRAM, wall time, final PSNR in the gates doc.

**Acceptance:** all 8 steps recorded in the gates doc with numbers; any failure files an issue and blocks T15.

---

### T15 — [ ] Tag v1.0.0 and publish the GitHub release

**Goal:** Cut the release. The detailed mechanics (AI-marker scrub, README badges, community files, Wiki, `gh release create`, post-release fresh-clone smoke, repo topics) already exist as a reviewed plan: [docs/superpowers/plans/2026-05-20-v1.0.0-release.md](docs/superpowers/plans/2026-05-20-v1.0.0-release.md) — execute its Phases 1, 2, 5, 6, 7, 8. Notes that supersede that plan where they conflict:
- Version bumps are already done by **T6** (its Phase 4 collapses to a verification grep).
- Its Phase 3 interactive walkthrough was already performed 2026-06-05 (findings F1–F11, all fixed or superseded) — replace with **T14**'s GPU smoke as the live gate.
- Test counts cited there (212) are stale — refresh every count from `pytest --collect-only -q` at execution time (216+ before T7 removes docker tests).
- `CHANGELOG.md` now exists at repo root (this audit created it) — update the `[Unreleased]` section to `[1.0.0] — <date>` instead of synthesizing from scratch.

**Acceptance:** `gh release view v1.0.0` shows the published release; fresh-clone install + `pytest` passes at the tag; CI badge green.

---

## Post-1.0 (not release-gated — file as issues)

- Alembic migrations to replace the manual `ALTER TABLE` shims in `backend/db/database.py` (grep `mesh_glb_path`).
- Rebalance reconstruction progress so COLMAP doesn't own 0–95% and training 95–100%.
- Process isolation for GPU training (currently a daemon thread inside the API process; `_GPU_LOCK` serializes jobs).
- `frames_registered` DB column populated from the trainer result (column exists, never set).
- `processed/` static mount in [backend/main.py:62](backend/main.py) resolves from CWD while config dirs resolve from config.yaml's directory — unify.
- Error message truncation at 500 chars (grep `\[:500\]` in reconstruction.py) can cut off long COLMAP errors.
- SuGaR mesh export remains optional/manual (no installable PyPI package — see gates doc).
