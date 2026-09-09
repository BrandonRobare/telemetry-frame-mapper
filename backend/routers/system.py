from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass

import psutil
from fastapi import APIRouter

from backend.services import accelerator
from backend.services.splat_backends import get_training_backend

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
    "torch": {"label": "PyTorch"},
    "gsplat": {"label": "gsplat"},
    "msplat": {"label": "msplat"},
    "sugar": {"label": "SuGaR"},
    "transformers": {"label": "transformers"},
}

_CUDA_SETUP_URL = (
    "https://github.com/BrandonRobare/telemetry-frame-mapper/blob/main/docs/SETUP.md"
)
_INSTALL_URL = (
    "https://github.com/BrandonRobare/telemetry-frame-mapper/blob/main/docs/INSTALL.md"
)


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
        "install_hint": None,
        "error": error,
    }


def _module_available(*names: str) -> bool:
    return any(importlib.util.find_spec(name) is not None for name in names)


def _python_install_guidance(
    key: str, accelerator_kind: str
) -> tuple[dict[str, str], str | None]:
    if key == "transformers":
        return {"project": "uv sync --frozen --group backend --group semantic"}, None
    if key == "torch":
        if accelerator_kind == "cuda":
            return {}, f"CUDA setup is toolkit-specific; follow {_CUDA_SETUP_URL}."
        platform_key = "macos" if accelerator_kind == "metal" else "cpu"
        return {platform_key: "uv pip install torch torchvision"}, None
    if key == "gsplat":
        if accelerator_kind == "cuda":
            return {}, f"gsplat needs the validated CUDA build matrix; follow {_CUDA_SETUP_URL}."
        if accelerator_kind == "metal":
            return {}, "gsplat is CUDA-only; Apple-Silicon splat training uses msplat."
        return {}, "gsplat requires a usable CUDA accelerator."
    if key == "msplat":
        return {}, (
            "msplat requires arm64 macOS 14+ with Python 3.12–3.13; "
            f"follow {_INSTALL_URL}."
        )
    if key == "sugar":
        if accelerator_kind == "cuda":
            return {}, f"SuGaR requires the validated CUDA stack; follow {_CUDA_SETUP_URL}."
        return {}, "SuGaR refinement requires CUDA."
    raise KeyError(f"Unknown Python dependency guidance key: {key}")


def _python_dependency_statuses(accelerator_kind: str) -> dict[str, dict[str, object]]:
    torch_available = _module_available("torch")
    gsplat_installed = _module_available("gsplat")
    msplat_installed = _module_available("msplat")
    backend_override = "metal" if accelerator_kind == "metal" else "cuda"
    splat_available = get_training_backend(backend_override).is_available()
    gsplat_available = splat_available and accelerator_kind != "metal"
    msplat_available = splat_available and accelerator_kind == "metal"
    if gsplat_available:
        gsplat_error = None
    elif gsplat_installed:
        gsplat_error = (
            "gsplat is installed but no compatible CUDA accelerator or compiled backend is "
            "available"
        )
    else:
        gsplat_error = "gsplat is not installed"
    if msplat_available:
        msplat_error = None
    elif msplat_installed:
        msplat_error = (
            "msplat is installed but no supported Apple-Silicon Metal runtime is available"
        )
    else:
        msplat_error = "msplat is not installed"
    sugar_available = shutil.which("sugar_trainers") is not None or _module_available(
        "sugar_scene", "sugar_utils"
    )
    transformers_available = _module_available("transformers", "safetensors")

    guidance = {
        key: _python_install_guidance(key, accelerator_kind) for key in PYTHON_DEPENDENCIES
    }
    statuses: dict[str, dict[str, object]] = {
        "torch": {
            "key": "torch",
            "label": PYTHON_DEPENDENCIES["torch"]["label"],
            "available": torch_available,
            "version": None,
            "path": None,
            "install_commands": guidance["torch"][0],
            "install_hint": guidance["torch"][1],
            "error": None,
        },
        "gsplat": {
            "key": "gsplat",
            "label": PYTHON_DEPENDENCIES["gsplat"]["label"],
            "available": gsplat_available,
            "version": None,
            "path": None,
            "install_commands": guidance["gsplat"][0],
            "install_hint": guidance["gsplat"][1],
            "error": gsplat_error,
        },
        "msplat": {
            "key": "msplat",
            "label": PYTHON_DEPENDENCIES["msplat"]["label"],
            "available": msplat_available,
            "version": None,
            "path": None,
            "install_commands": guidance["msplat"][0],
            "install_hint": guidance["msplat"][1],
            "error": msplat_error,
        },
        "sugar": {
            "key": "sugar",
            "label": PYTHON_DEPENDENCIES["sugar"]["label"],
            "available": sugar_available,
            "version": None,
            "path": shutil.which("sugar_trainers"),
            "install_commands": guidance["sugar"][0],
            "install_hint": guidance["sugar"][1],
            "error": None,
        },
        "transformers": {
            "key": "transformers",
            "label": PYTHON_DEPENDENCIES["transformers"]["label"],
            "available": transformers_available,
            "version": None,
            "path": None,
            "install_commands": guidance["transformers"][0],
            "install_hint": guidance["transformers"][1],
            "error": None,
        },
    }

    # The selected trainer's cached probe is the source of truth for splat usability.
    # It checks native capability without starting a training/JIT workload.
    # SuGaR remains import-spec-only because it has no equivalent capability probe.
    if torch_available:
        try:
            import torch  # type: ignore

            statuses["torch"].update(
                {
                    "version": getattr(torch, "__version__", None),
                    "path": getattr(torch, "__file__", None),
                }
            )
        except Exception as exc:  # pragma: no cover - depends on local installation
            statuses["torch"].update({"available": False, "error": str(exc)})

    if gsplat_installed:
        spec = importlib.util.find_spec("gsplat")
        origin = getattr(spec, "origin", None)
        if origin is not None:
            statuses["gsplat"]["path"] = origin
    if msplat_installed:
        spec = importlib.util.find_spec("msplat")
        origin = getattr(spec, "origin", None)
        if origin is not None:
            statuses["msplat"]["path"] = origin
    if statuses["sugar"]["available"]:
        spec = importlib.util.find_spec("sugar_scene")
        origin = getattr(spec, "origin", None)
        if origin is not None:
            statuses["sugar"]["path"] = origin

    return statuses


def _accelerator_status(
    hardware: dict[str, str],
    python_deps: dict[str, dict[str, object]],
    gpu: dict[str, object],
) -> dict[str, object]:
    kind = hardware["kind"]
    backend = (
        "cuda_gsplat"
        if python_deps["gsplat"]["available"]
        else "metal_msplat"
        if python_deps["msplat"]["available"]
        else None
    )
    if kind == "cuda":
        description = str(gpu["name"] or "CUDA accelerator")
    elif kind == "metal":
        description = "Apple Metal"
    else:
        description = "CPU"
    return {
        "kind": kind,
        "device": hardware["device"],
        "description": description,
        "splat_backend": backend,
        "splat_backend_available": backend is not None,
    }


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
    accelerator_info: dict[str, object],
) -> list[dict[str, object]]:
    ffmpeg = bool(binaries["ffmpeg"]["available"])
    exiftool = bool(binaries["exiftool"]["available"])
    colmap = bool(binaries["colmap"]["available"])
    torch_available = bool(python_deps["torch"]["available"])
    accelerator_kind = str(accelerator_info["kind"])
    splat_backend_available = bool(accelerator_info["splat_backend_available"])
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
            "available": colmap and splat_backend_available,
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("splat_backend", splat_backend_available),
                )
                if not ok
            ],
        },
        {
            "key": "sugar_refinement",
            "label": "SuGaR refinement",
            "available": colmap and accelerator_kind == "cuda" and torch_available and sugar,
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("accelerator_cuda", accelerator_kind == "cuda"),
                    ("torch", torch_available),
                    ("sugar", sugar),
                )
                if not ok
            ],
        },
        {
            "key": "semantic_labeling",
            "label": "Semantic labeling",
            "available": (
                colmap
                and accelerator_kind == "cuda"
                and splat_backend_available
                and transformers
            ),
            "missing": [
                key
                for key, ok in (
                    ("colmap", colmap),
                    ("accelerator_cuda", accelerator_kind == "cuda"),
                    ("splat_backend", splat_backend_available),
                    ("transformers", transformers),
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

    hardware = accelerator.describe()
    gpu = _gpu_status()
    binaries = {check.key: _binary_status(check) for check in BINARY_CHECKS}
    python_deps = _python_dependency_statuses(hardware["kind"])
    accelerator_info = _accelerator_status(hardware, python_deps, gpu)

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
        "accelerator": accelerator_info,
        "tools": [*binaries.values(), *python_deps.values()],
        "workflows": _workflow_statuses(binaries, python_deps, accelerator_info),
        "colmap_available": binaries["colmap"]["available"],
        "colmap_capabilities": colmap_probe,
        "splat_transform_available": bool(splat_transform_probe.get("available")),
    }
