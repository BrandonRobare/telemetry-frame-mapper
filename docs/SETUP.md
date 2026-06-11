# Setup Guide

## GPU splat training (Windows)

Splat training is optional — without it, reconstructions still complete with a COLMAP
sparse cloud (`colmap_only`). To train gaussian splats on an NVIDIA GPU:

### Prerequisites

1. NVIDIA driver for a CUDA-capable GPU
2. CUDA Toolkit 13.x (`nvcc --version` should work in a fresh terminal)
3. MSVC Build Tools with the "Desktop development with C++" workload (`cl.exe`)

### Install

torch and gsplat are intentionally **not** part of the `[reconstruction]` extra:
CUDA-enabled torch wheels are not on the default PyPI index, and gsplat's sdist requires
torch already installed at build time. Install in two steps, then the extras:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu130
pip install gsplat --index-url https://docs.gsplat.studio/whl/pt29cu130 --extra-index-url https://pypi.org/simple
pip install -e ".[backend,reconstruction]"
```

Notes:

- The torch and `nvcc` CUDA **major versions must match**: CUDA Toolkit 13.2 pairs with
  `cu130` wheels, not `cu12x`.
- If no prebuilt gsplat wheel matches your torch/CUDA combination, gsplat JIT-compiles its
  CUDA kernels on **first import** (5–15 minutes; needs `cl.exe` and `nvcc` on PATH; set
  `TORCH_CUDA_ARCH_LIST=8.6` for an RTX 3050 Ti).
- Warm up once with `python -c "import gsplat"` before starting the first training job so
  the JIT compile doesn't eat into it.

## External Binaries

Required for the CLI release gate:

- **ffmpeg** — DJI MP4 video/SRT extraction. It must be on `PATH` or passed with `--ffmpeg`.
- **exiftool** — GPS EXIF writing. It must be on `PATH` or passed with `--exiftool`.

Optional/manual reconstruction tools:

- **colmap** — Structure from Motion for Reconstruct tab jobs. Missing COLMAP should fail the reconstruction job with clear install/PATH guidance, not break backend import.
- **torch + gsplat** + CUDA-capable GPU — Gaussian splat training and optional server-side video rendering. Manual two-step install (see the GPU section above); intentionally not included in the Python `reconstruction` extra.
- **SuGaR** (`sugar_scene`/`sugar`) — mesh export only. It is a manual upstream install and is not included in the Python `reconstruction` extra.

CI should use fakes/mocks for external binaries and optional reconstruction libraries. Real `ffmpeg`/`exiftool` smoke is must-pass for v1.0; real COLMAP/gsplat/SuGaR/video-render smoke is optional/manual unless reconstruction is promoted to production-ready.
