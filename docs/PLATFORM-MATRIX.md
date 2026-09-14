# Platform feature matrix (v3.0)

One-table capabilities across distribution and hardware boundaries, per #791/#818.

| Capability | Source (Linux/Mac dev) | Windows installer | Docker image | macOS bundled app (arm64, macOS 14+, Python 3.12/3.13) |
|---|---|---|---|---|
| CLI geotagging (ffmpeg + exiftool) | ✅ | ✅ | ✅ | ✅ (Homebrew tools discovered at runtime) |
| Import / review / coverage / mission planning | ✅ | ✅ | ✅ | ✅ |
| GPS sync, session logs, defects, compare | ✅ | ✅ | ✅ | ✅ |
| COLMAP reconstruction | ✅ w/ COLMAP on PATH | ✅ w/ COLMAP on PATH | ✅ (bundled) | ✅ w/ COLMAP installed |
| `colmap_only` output | ✅ | ✅ | ✅ | ✅ |
| Semantic segmentation (per-frame, CPU) | ✅ (transformers group) | ⚠️ install `semantic` group manually | ✅ (since #872) | ✅ |
| Native splat training — CUDA | ⚠️ manual torch/gsplat, NVIDIA GPU | ⚠️ manual | ⚭ not installed | — |
| Native splat training — Metal (msplat) | — | — | — | ✅ on arm64 + macOS 14+ + Py 3.12/3.13 |
| Splat viewing / annotations / measurements / flythrough | ✅ | ✅ (CUDA-trained splats) | ✅ | ✅ |
| Exports (survey report, geopackage, KML, USD, potree, orthomosaic) | ✅ | ✅ | ✅ | ✅ |
| Per-Gaussian semantic labeling | CUDA-only (expected-depth rendering) | CUDA-only | — | ✕ (boundary per #791) |

## Boundary notes

- **Per-frame CPU segmentation** (six super-categories) works everywhere the `semantic`
  dependency group is installed.
- **Per-Gaussian splat labeling** requires CUDA expected-depth rendering through the CUDA renderer
  and is outside the supported Mac scope.
- The full Mac floor is: Apple Silicon (arm64), macOS 14+, Python 3.12 or 3.13. Everything above
  except Metal training also works on older/non-arm64 setups; Metal training cannot install there
  (msplat ships `macosx_14_0_arm64` cp312/cp313 wheels only).