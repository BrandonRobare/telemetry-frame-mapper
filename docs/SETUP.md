# Setup Guide

## GPU splat training (Windows)

Splat training is optional — without it, reconstructions still complete with a COLMAP
sparse cloud (`colmap_only`). To train gaussian splats on an NVIDIA GPU:

### Prerequisites

1. NVIDIA driver for a CUDA-capable GPU
2. CUDA Toolkit 13.x (`nvcc --version` should work in a fresh terminal)
3. MSVC Build Tools with the "Desktop development with C++" workload (`cl.exe`)

### Install (verified 2026-06-12 on RTX 3050 Ti / Windows 11 / CUDA Toolkit 13.2 / VS 2022)

torch and gsplat are intentionally **not** part of the `[reconstruction]` extra:
CUDA-enabled torch wheels are not on the default PyPI index, and gsplat's sdist requires
torch already installed at build time.

```bash
# 1. Pin the torch version. gsplat 1.5.3 uses a private torch JIT API that changed in
#    newer torch; torch 2.12 fails with "_jit_compile() missing ... 'with_sycl'".
pip install "torch==2.9.1" --index-url https://download.pytorch.org/whl/cu130

# 2. gsplat installs from sdist. No prebuilt wheel matches modern stacks (the official
#    wheel index tops out at Python 3.10 / torch 2.4 / cu124 for Windows), and the sdist
#    must see the venv's torch, hence --no-build-isolation.
pip install ninja
pip install gsplat --no-build-isolation

# 3. The rest of the optional extras
pip install -e ".[backend,reconstruction]"
```

The CUDA kernels JIT-compile on the **first rasterization call** (not on `import gsplat`,
which succeeds in seconds without compiling anything). Warm up once from a
**VS x64 Developer Command Prompt** (`vcvars64.bat` — `cl.exe` must be on PATH):

```bat
set "TORCH_CUDA_ARCH_LIST=8.6"
set "NVCC_APPEND_FLAGS=-Xcompiler /Zc:preprocessor"
python -c "import torch, gsplat; d='cuda'; import torch.nn.functional as F; n=8; gsplat.rasterization(means=torch.randn(n,3,device=d), quats=F.normalize(torch.randn(n,4,device=d),dim=-1), scales=torch.rand(n,3,device=d)*0.1, opacities=torch.rand(n,device=d), colors=torch.rand(n,1,3,device=d), viewmats=torch.eye(4,device=d)[None], Ks=torch.tensor([[[100.,0.,32.],[0.,100.,32.],[0.,0.,1.]]],device=d), width=64, height=64, sh_degree=0, packed=True)"
```

### Semantic-labeling GPU smoke

After a quick-preset reconstruction completes with a `splat.ply`, warm up ED-mode
rasterization before running semantic labels. This mirrors the gsplat JIT check but
asserts the expected-depth output is present and positive:

```bat
python -c "import torch, gsplat; d='cuda'; import torch.nn.functional as F; n=8; renders,_,_=gsplat.rasterization(means=torch.randn(n,3,device=d), quats=F.normalize(torch.randn(n,4,device=d),dim=-1), scales=torch.rand(n,3,device=d)*0.1, opacities=torch.rand(n,device=d), colors=torch.rand(n,1,3,device=d), viewmats=torch.eye(4,device=d)[None], Ks=torch.tensor([[[100.,0.,32.],[0.,100.,32.],[0.,0.,1.]]],device=d), width=64, height=64, render_mode='ED', sh_degree=0, packed=True); assert renders.shape[1:3] == (64,64); assert torch.isfinite(renders).all(); assert renders[...,0].max() > 0"
```

Then start the backend and request labeling for the reconstruction id:

```bat
curl -X POST http://localhost:8000/reconstruction/RECONSTRUCTION_ID/semantic-labels
```

On the validated RTX 3050 Ti target, a normal quick-preset survey should finish in
under two minutes after kernels are warm, and `/reconstruction/RECONSTRUCTION_ID/semantic-labels`
should report less than 30% `unlabeled` for a typical well-covered scene.

Known issues (all hit during the v1.0 release validation):

- The torch and `nvcc` CUDA **major versions must match**: CUDA Toolkit 13.2 pairs with
  `cu130` wheels, not `cu12x`.
- `TORCH_CUDA_ARCH_LIST` is `8.6` for an RTX 3050 Ti. Use the quoted `set "VAR=value"`
  form in cmd — a trailing space before `&&` becomes part of the value and torch fails
  with `Unknown CUDA arch ()`.
- `NVCC_APPEND_FLAGS=-Xcompiler /Zc:preprocessor` is required with CUDA 13.x: its CCCL
  headers reject MSVC's traditional preprocessor (`fatal error C1189`).
- **gsplat 1.5.3 MSVC patch:** the build passes the GCC-only flag `-Wno-attributes` to
  `cl.exe`, which fails with `error D8021`. Until fixed upstream, edit
  `site-packages/gsplat/cuda/_backend.py` (~line 177):
  `extra_cflags = [opt_level]` on Windows instead of `[opt_level, "-Wno-attributes"]`.
- The compile takes ~5 minutes on a typical laptop; the cached build under
  `%LOCALAPPDATA%` is reused afterwards.
- **Run the backend itself from a VS x64 Developer Command Prompt** (`cl.exe` on PATH),
  not just the warm-up. Even with kernels cached, torch's extension loader re-runs a
  `where cl` compiler-ABI check on every load — a backend started without `cl.exe` fails
  the first training job at "loading COLMAP model" with
  `Command '['where', 'cl']' returned non-zero exit status 1` (COLMAP succeeds; only
  training dies). Validated on the v1.0 full-preset run (gates doc step 8).

## External Binaries

Required for the CLI release gate:

- **ffmpeg** — DJI MP4 video/SRT extraction. It must be on `PATH` or passed with `--ffmpeg`.
- **exiftool** — GPS EXIF writing. It must be on `PATH` or passed with `--exiftool`.

Optional/manual reconstruction tools:

- **colmap** — Structure from Motion for Reconstruct tab jobs. Missing COLMAP should fail the reconstruction job with clear install/PATH guidance, not break backend import.
- **torch + gsplat** + CUDA-capable GPU — Gaussian splat training and optional server-side video rendering. Manual two-step install (see the GPU section above); intentionally not included in the Python `reconstruction` extra.
- **SuGaR** (`sugar_scene`/`sugar`) — mesh export only. [SuGaR](https://github.com/Anttwo/SuGaR) has no pip-installable release; it must be installed manually by cloning that repo, and is not included in the Python `reconstruction` extra. Mesh export is optional — splat viewing and the rest of reconstruction work fine without it.

CI should use fakes/mocks for external binaries and optional reconstruction libraries. Real `ffmpeg`/`exiftool` smoke is must-pass for v1.0; real COLMAP/gsplat/SuGaR/video-render smoke is optional/manual unless reconstruction is promoted to production-ready.

## Optional remote GPU worker

Remote execution is off by default. It is intended for an operator-controlled worker on a private,
authenticated network; this backend does not provision workers, copy image bytes, or expose a worker
to the public internet. The API server and worker must see the same `imports_dir`, `data_dir`, and
`exports_dir` paths (for example via a mounted shared volume).

Set only the endpoint settings in `config.yaml`, then place the bearer token in the environment named
by `auth_token_env` before starting the backend. Do not put tokens in YAML, documentation, or shell
history. HTTPS is required; `allow_insecure_http: true` is only for an isolated development network.

```yaml
remote_worker:
  enabled: true
  url: "https://gpu-worker.internal"
  auth_token_env: "REMOTE_WORKER_TOKEN"
  timeout_seconds: 10
  poll_interval_seconds: 2
  allow_insecure_http: false
```

The worker implements this small JSON protocol:

- `POST /v1/reconstructions` receives `local_job_id`, `reconstruction_id`, `preset`, `colmap_dir`,
  and `image_ids`, and returns `202 {"job_id": "..."}`.
- `GET /v1/reconstructions/{job_id}` returns a status object: `queued` or `running` with optional
  `step` and `progress_pct`; `complete` with optional `result.frames_registered`, `gaussian_count`,
  `psnr`, and `ssim`; or `failed`/`cancelled` with an `error`.
- `POST /v1/reconstructions/{job_id}/cancel` requests cancellation.

The local durable queue saves the returned worker job id and resumes polling it after a retry, so a
temporary API-side failure does not submit a duplicate reconstruction. The Jobs queue API exposes
that remote job id for diagnostics. A worker must write artifacts to the shared configured paths;
artifact transfer and arbitrary worker-supplied local paths are intentionally out of scope.
