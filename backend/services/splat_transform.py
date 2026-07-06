"""Splat post-processing via @playcanvas/splat-transform (Node/npx subprocess).

Capability-gated: detects Node.js (or npx) at probe time and exposes
availability via `splat_transform_available()`.  All operations call the
CLI as a subprocess — no npm install is required at import time.

Operations:
- cleanup: NaN/inf removal, opacity-floor filtering, SH-band stripping,
  spatial crop, decimation, Morton reorder → cleaned standard PLY
- compress: optional SPZ/SOG export for external sharing.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# probe module-level singleton — populated lazily
_PROBE: dict[str, object] | None = None


@lru_cache(maxsize=1)
def _probe_node() -> dict[str, object]:
    """Detect Node.js / npx availability for splat-transform.

    Returns:
        available: bool — at least one of node or npx found
        node_path: str | None
        npx_path: str | None
        version: str | None — first line of node --version
    """
    node_path = shutil.which("node")
    npx_path = shutil.which("npx")
    version = None
    if node_path:
        try:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            version = (result.stdout.strip() or result.stderr.strip()) or None
        except Exception:
            pass
    return {
        "available": node_path is not None and npx_path is not None,
        "node_path": node_path,
        "npx_path": npx_path,
        "version": version,
    }


def splat_transform_available() -> dict[str, object]:
    """Return the cached Node probe result."""
    global _PROBE
    if _PROBE is None:
        _PROBE = _probe_node()
    return _PROBE


def clear_splat_transform_cache() -> None:
    global _PROBE
    _PROBE = None
    _probe_node.cache_clear()


def _run_splat_transform(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run ``npx @playcanvas/splat-transform <args>`` and return the CompletedProcess.

    Raises RuntimeError if Node/npx are not available.
    """
    probe = splat_transform_available()
    if not probe["available"]:
        raise RuntimeError(
            "splat-transform requires Node.js and npx. Install Node.js (>=18) "
            "and ensure it is on PATH."
        )
    npx = str(probe["npx_path"])
    cmd = [npx, "@playcanvas/splat-transform", *args]
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def cleanup_splat(
    src: Path,
    dst: Path,
    *,
    opacity_floor: float | None = 0.01,
    sh_bands: int | None = 0,
    decimate: float | None = None,
    morton: bool = True,
) -> subprocess.CompletedProcess:
    """Run splat-transform cleanup on *src*, writing cleaned PLY to *dst*.

    Parameters:
        opacity_floor: Remove gaussians below this opacity threshold (default 0.01).
            Set to None to skip opacity filtering.
        sh_bands: Number of SH bands to keep (0 = DC only, None = all bands).
        decimate: Keep ratio (0.0–1.0) for random decimation.
        morton: Apply Morton reorder (true by default).

    Returns the subprocess CompletedProcess; raises RuntimeError on failure.
    """
    args = ["cleanup", str(src), str(dst)]
    if opacity_floor is not None:
        args += ["--opacity-floor", str(opacity_floor)]
    if sh_bands is not None:
        args += ["--sh-bands", str(sh_bands)]
    if decimate is not None:
        args += ["--decimate", str(decimate)]
    if morton:
        args.append("--morton")
    return _run_splat_transform(args)


def compress_splat(
    src: Path,
    dst: Path,
    format: str = "spz",
    *,
    quality: int | None = None,
) -> subprocess.CompletedProcess:
    """Compress a PLY splat to SPZ or SOG format for external sharing.

    Args:
        src: Source PLY path.
        dst: Output path (must end with .spz or .sog).
        format: "spz" (default) or "sog".
        quality: Compression quality 1–100 (SPZ only).
    """
    args = ["compress", str(src), str(dst)]
    if format and format != "spz":
        args += ["--format", format]
    if quality is not None:
        args += ["--quality", str(quality)]
    return _run_splat_transform(args)