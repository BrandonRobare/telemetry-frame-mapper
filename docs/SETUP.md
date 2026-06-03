# Setup Guide

## GPU Acceleration (optional)

Reconstruction runs on CPU by default. To use NVIDIA GPU acceleration:

### Prerequisites

1. NVIDIA driver ≥ 525.60
2. [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)

```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### Running with GPU

```bash
docker compose --profile nvidia up
```

Without the `--profile nvidia` flag, the backend runs in CPU-only mode.

## External Binaries

Required for the CLI release gate:

- **ffmpeg** — DJI MP4 video/SRT extraction. It must be on `PATH` or passed with `--ffmpeg`.
- **exiftool** — GPS EXIF writing. It must be on `PATH` or passed with `--exiftool`.

Optional/manual reconstruction tools:

- **colmap** — Structure from Motion for Reconstruct tab jobs. Missing COLMAP should fail the reconstruction job with clear install/PATH guidance, not break backend import.
- **gsplat** + CUDA-capable GPU — Gaussian splat training and optional server-side video rendering. Install the Python extra with `pip install -e ".[backend,reconstruction]"` for local reconstruction validation.
- **SuGaR** (`sugar_scene`/`sugar`) — mesh export only. It is a manual upstream install and is not included in the Python `reconstruction` extra.

CI should use fakes/mocks for external binaries and optional reconstruction libraries. Real `ffmpeg`/`exiftool` smoke is must-pass for v1.0; real COLMAP/gsplat/SuGaR/video-render smoke is optional/manual unless reconstruction is promoted to production-ready.
