from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass

import psutil
from fastapi import APIRouter

try:
    import pynvml

    pynvml.nvmlInit()
    _NVML_AVAILABLE = True
except Exception:
    pynvml = None  # type: ignore[assignment]
    _NVML_AVAILABLE = False

router = APIRouter(prefix="/system", tags=["system"])


@dataclass(frozen=True)
class BinaryCheck:
    key: str
    label: str
    executable: str
    version_args: tuple[str, ...]
    install: dict[str, str]


BINARY_CHECKS = (
    BinaryCheck(
        key="ffmpeg",
        label="FFmpeg",
        executable="ffmpeg",
        version_args=("-version",),
        install={
            "macos": "brew install ffmpeg",
            "ubuntu": "sudo apt install ffmpeg",
            "windows": "winget install Gyan.FFmpeg",
        },
    ),
    BinaryCheck(
        key="exiftool",
        label="ExifTool",
        executable="exiftool",
        version_args=("-ver",),
        install={
            "macos": "brew install exiftool",
            "ubuntu": "sudo apt install libimage-exiftool-perl",
            "windows": "winget install OliverBetz.ExifTool",
        },
    ),
    BinaryCheck(
        key="colmap",
        label="COLMAP",
        executable="colmap",
        version_args=("-h",),
        install={
            "macos": "brew install colmap",
            "ubuntu": "sudo apt install colmap",
            "windows": "winget install COLMAP.COLMAP",
        },
    ),
)

PYTHON_DEPENDENCIES = {
    "torch": {
        "label": "PyTorch",
        "install": {
            "cuda": "uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124",
            "cpu": "uv pip install torch torchvision",
        },
    },
    "gsplat": {
        "label": "gsplat",
        "install": {"pip": "uv pip install gsplat"},
    },
    "sugar": {
        "label": "SuGaR",
        "install": {"pip": "uv pip install git+https://github.com/Anttwo/SuGaR.git"},
    },
    "transformers": {
        "label": "transformers",
        "install": {"pip": "uv pip install -e '.[semantic]'"},
    },
}


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:160]
    return None


def _binary_status(check: BinaryCheck) -> dict[str, object]:
    path = shutil.which(check.executable)
    version = None
    error = None
    if path:
        try:
            completed = subprocess.run(
                [path, *check.version_args],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            version = _first_line(completed.stdout) or _first_line(completed.stderr)
        except Exception as exc:  # pragma: no cover - defensive around local tools
            error = str(exc)
    return {
        "key": check.key,
        "label": check.label,
        "available": path is not None,
        "path": path,
        "version": version,
        "install_commands": check.install,
        "error": error,
    }


def _module_available(*names: str) -> bool:
    return any(importlib.util.find_spec(name) is not None for name in names)


def _python_dependency_statuses() -> dict[str, dict[str, object]]:
    torch_available = _module_available("torch")
    gsplat_available = _module_available("gsplat")
    sugar_available = shutil.which("sugar_trainers") is not None or _module_available(
        "sugar_scene", "sugar_utils"
    )
    transformers_available = _module_available("transformers", "safetensors")

    statuses: dict[str, dict[str, object]] = {
        "torch": {
            "key": "torch",
            "label": PYTHON_DEPENDENCIES["torch"]["label"],
            "available": torch_available,
            "version": None,
            "path": None,
            "cuda_available": False,
            "install_commands": PYTHON_DEPENDENCIES["torch"]["install"],
            "error": None,
        },
        "gsplat": {
            "key": "gsplat",
            "label": PYTHON_DEPENDENCIES["gsplat"]["label"],
            "available": gsplat_available,
            "version": None,
            "path": None,
            "install_commands": PYTHON_DEPENDENCIES["gsplat"]["install"],
            "error": None,
        },
        "sugar": {
            "key": "sugar",
            "label": PYTHON_DEPENDENCIES["sugar"]["label"],
            "available": sugar_available,
            "version": None,
            "path": shutil.which("sugar_trainers"),
            "install_commands": PYTHON_DEPENDENCIES["sugar"]["install"],
            "error": None,
        },
        "transformers": {
            "key": "transformers",
            "label": PYTHON_DEPENDENCIES["transformers"]["label"],
            "available": transformers_available,
            "version": None,
            "path": None,
            "install_commands": PYTHON_DEPENDENCIES["transformers"]["install"],
            "error": None,
        },
    }

    # Avoid importing gsplat/SuGaR here: gsplat may trigger CUDA extension work in some
    # environments. Torch import is the only reliable way to expose CUDA state/version.
    if torch_available:
        try:
            import torch  # type: ignore

            statuses["torch"].update(
                {
                    "version": getattr(torch, "__version__", None),
                    "path": getattr(torch, "__file__", None),
                    "cuda_available": bool(torch.cuda.is_available()),
                }
            )
        except Exception as exc:  # pragma: no cover - depends on local installation
            statuses["torch"].update({"available": False, "error": str(exc)})

    for key in ("gsplat", "sugar"):
        if statuses[key]["available"]:
            spec = importlib.util.find_spec("gsplat" if key == "gsplat" else "sugar_scene")
            origin = getattr(spec, "origin", None)
            if origin is not None:
                statuses[key]["path"] = origin

    return statuses


def _gpu_status() -> dict[str, object]:
    status: dict[str, object] = {
        "available": False,
        "name": None,
        "gpu_pct": None,
        "vram_used_gb": None,
        "vram_total_gb": None,
    }
    if _NVML_AVAILABLE and pynvml is not None:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            status.update(
                {
                    "available": True,
                    "name": name,
                    "gpu_pct": float(util.gpu),
                    "vram_used_gb": round(mem_info.used / 1024**3, 2),
                    "vram_total_gb": round(mem_info.total / 1024**3, 2),
                }
            )
        except Exception:
            pass
    return status


def _workflow_statuses(
    binaries: dict[str, dict[str, object]],
    python_deps: dict[str, dict[str, object]],
    gpu: dict[str, object],
) -> list[dict[str, object]]:
    ffmpeg = bool(binaries["ffmpeg"]["available"])
    exiftool = bool(binaries["exiftool"]["available"])
    colmap = bool(binaries["colmap"]["available"])
    torch_cuda = bool(python_deps["torch"].get("cuda_available"))
    gsplat = bool(python_deps["gsplat"]["available"])
    gpu_available = bool(gpu["available"])
    sugar = bool(python_deps["sugar"]["available"])
    transformers = bool(python_deps["transformers"]["available"])

    return [
        {
            "key": "video_geotagging",
            "label": "Video geotagging",
            "available": ffmpeg and exiftool,
            "missing": [key for key, ok in (("ffmpeg", ffmpeg), ("exiftool", exiftool)) if not ok],
        },
        {
            "key": "colmap_reconstruction",
            "label": "COLMAP reconstruction",
            "available": colmap,
            "missing": [] if colmap else ["colmap"],
        },
        {
            "key": "gaussian_splat_training",
            "label": "Gaussian splat training",
            "available": colmap and torch_cuda and gsplat and gpu_available,
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("torch_cuda", torch_cuda),
                    ("gsplat", gsplat),
                    ("nvidia_gpu", gpu_available),
                )
                if not ok
            ],
        },
        {
            "key": "sugar_refinement",
            "label": "SuGaR refinement",
            "available": colmap and torch_cuda and sugar and gpu_available,
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("torch_cuda", torch_cuda),
                    ("sugar", sugar),
                    ("nvidia_gpu", gpu_available),
                )
                if not ok
            ],
        },
        {
            "key": "semantic_labeling",
            "label": "Semantic labeling",
            "available": colmap and torch_cuda and gsplat and transformers and gpu_available,
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("torch_cuda", torch_cuda),
                    ("gsplat", gsplat),
                    ("transformers", transformers),
                    ("nvidia_gpu", gpu_available),
                )
                if not ok
            ],
        },
    ]


@router.get("/resources")
def get_resources():
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(".")
    io = psutil.disk_io_counters()
    disk_io_mbps = None
    if io:
        disk_io_mbps = round((io.read_bytes + io.write_bytes) / 1024 / 1024, 2)

    gpu = _gpu_status()
    binaries = {check.key: _binary_status(check) for check in BINARY_CHECKS}
    python_deps = _python_dependency_statuses()

    colmap_probe: dict[str, object] = {}
    try:
        from backend.services.colmap_capabilities import get_capabilities as _colmap_cap

        colmap_probe = _colmap_cap()
    except Exception:  # pragma: no cover
        colmap_probe = {}

    splat_transform_probe: dict[str, object] = {}
    try:
        from backend.services.splat_transform import splat_transform_available as _st_probe

        splat_transform_probe = _st_probe()
    except Exception:  # pragma: no cover
        splat_transform_probe = {}

    return {
        "cpu_pct": cpu_pct,
        "ram_used_gb": round(mem.used / 1024**3, 2),
        "ram_total_gb": round(mem.total / 1024**3, 2),
        "disk_used_gb": round(disk.used / 1024**3, 2),
        "disk_total_gb": round(disk.total / 1024**3, 2),
        "disk_io_mbps": disk_io_mbps,
        "gpu_pct": gpu["gpu_pct"],
        "vram_used_gb": gpu["vram_used_gb"],
        "vram_total_gb": gpu["vram_total_gb"],
        "gpu_name": gpu["name"],
        "gpu_available": gpu["available"],
        "tools": [*binaries.values(), *python_deps.values()],
        "workflows": _workflow_statuses(binaries, python_deps, gpu),
        "colmap_available": binaries["colmap"]["available"],
        "colmap_capabilities": colmap_probe,
        "splat_transform_available": bool(splat_transform_probe.get("available")),
        # Spec lookup only — importing gsplat can trigger a multi-minute CUDA JIT compile.
        "gsplat_available": python_deps["gsplat"]["available"],
    }
