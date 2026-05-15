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

The following binaries must be on `PATH` (or configured via `config.yaml`):

- **ffmpeg** — video extraction
- **exiftool** — EXIF writing
- **colmap** — Structure from Motion (required for reconstruction)
