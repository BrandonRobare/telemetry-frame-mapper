from __future__ import annotations

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


@router.get("/resources")
def get_resources():
    cpu_pct = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(".")
    io = psutil.disk_io_counters()
    disk_io_mbps = None
    if io:
        disk_io_mbps = round((io.read_bytes + io.write_bytes) / 1024 / 1024, 2)

    gpu_pct = None
    vram_used_gb = None
    vram_total_gb = None
    if _NVML_AVAILABLE and pynvml is not None:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_pct = float(util.gpu)
            vram_used_gb = round(mem_info.used / 1024 ** 3, 2)
            vram_total_gb = round(mem_info.total / 1024 ** 3, 2)
        except Exception:
            pass

    return {
        "cpu_pct": cpu_pct,
        "ram_used_gb": round(mem.used / 1024 ** 3, 2),
        "ram_total_gb": round(mem.total / 1024 ** 3, 2),
        "disk_used_gb": round(disk.used / 1024 ** 3, 2),
        "disk_total_gb": round(disk.total / 1024 ** 3, 2),
        "disk_io_mbps": disk_io_mbps,
        "gpu_pct": gpu_pct,
        "vram_used_gb": vram_used_gb,
        "vram_total_gb": vram_total_gb,
    }
