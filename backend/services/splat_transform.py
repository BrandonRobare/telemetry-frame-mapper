"""Splat post-processing via @playcanvas/splat-transform (Node/npx subprocess).

Capability-gated: detects Node.js/npx and the locked tool install at probe
time and exposes availability via `splat_transform_available()`.  All
operations call the CLI as a subprocess — nothing is installed at import time
or at run time.

The CLI version is pinned exactly in ``tools/splat-transform/package.json``
and locked (with integrity hashes for the whole dependency tree) in its
``package-lock.json``.  Install it once with
``npm ci --prefix tools/splat-transform``; every call then runs
``npx --no-install @playcanvas/splat-transform@<pinned>`` from that directory,
so npx uses the locked install and never downloads from the registry.

Operations:
- cleanup: NaN/inf removal, opacity-floor filtering, SH-band stripping,
  spatial crop, decimation, Morton reorder → cleaned standard PLY
- compress: optional SPZ/SOG export for external sharing.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

SPLAT_TRANSFORM_PACKAGE = "@playcanvas/splat-transform"
SPLAT_TRANSFORM_TOOL_DIR = Path(__file__).resolve().parents[2] / "tools" / "splat-transform"
SPLAT_TRANSFORM_INSTALL_HINT = (
    "Install the locked splat-transform CLI with `npm ci --prefix tools/splat-transform` "
    "(Node.js >= 22), then restart the backend."
)
_EXACT_VERSION = re.compile(r"\d+\.\d+\.\d+")

# probe module-level singleton — populated lazily
_PROBE: dict[str, object] | None = None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _pinned_version() -> str | None:
    """The exact version pinned in the tool directory's package.json (never a range)."""
    deps = _read_json(SPLAT_TRANSFORM_TOOL_DIR / "package.json").get("dependencies")
    version = deps.get(SPLAT_TRANSFORM_PACKAGE) if isinstance(deps, dict) else None
    if isinstance(version, str) and _EXACT_VERSION.fullmatch(version):
        return version
    return None


def _installed_version() -> str | None:
    installed = SPLAT_TRANSFORM_TOOL_DIR / "node_modules" / SPLAT_TRANSFORM_PACKAGE
    version = _read_json(installed / "package.json").get("version")
    return version if isinstance(version, str) else None


@lru_cache(maxsize=1)
def _probe_node() -> dict[str, object]:
    """Detect Node.js / npx and the locked splat-transform install.

    Returns:
        available: bool — node, npx and the pinned version's locked install found
        node_path: str | None
        npx_path: str | None
        version: str | None — first line of node --version
        pinned_version: str | None — exact version in tools/splat-transform/package.json
        installed_version: str | None — version installed in its node_modules
        reason: str | None — what is missing when unavailable
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
    pinned = _pinned_version()
    installed = _installed_version()
    reason = None
    if node_path is None or npx_path is None:
        reason = "splat-transform requires Node.js (>= 22) and npx on PATH."
    elif pinned is None:
        reason = "tools/splat-transform/package.json does not pin an exact splat-transform version."
    elif installed != pinned:
        reason = (
            f"splat-transform {pinned} is not installed"
            + (f" (found {installed})" if installed else "")
            + f". {SPLAT_TRANSFORM_INSTALL_HINT}"
        )
    return {
        "available": reason is None,
        "node_path": node_path,
        "npx_path": npx_path,
        "version": version,
        "pinned_version": pinned,
        "installed_version": installed,
        "reason": reason,
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
    """Run the pinned, locally installed splat-transform CLI and return the CompletedProcess.

    Runs ``npx --no-install @playcanvas/splat-transform@<pinned> <args>`` from the
    lockfile-installed tool directory: npx uses that install and refuses to download.
    File arguments must therefore be absolute.

    Raises RuntimeError if Node/npx or the locked install are not available, if the
    subprocess exits non-zero, or if it times out.  Callers may assume a returned
    CompletedProcess means the output file was written.
    """
    probe = splat_transform_available()
    if not probe["available"]:
        raise RuntimeError(
            str(probe.get("reason") or "")
            or "splat-transform requires Node.js (>= 22) and npx on PATH. "
            + SPLAT_TRANSFORM_INSTALL_HINT
        )
    pinned = _pinned_version()
    if pinned is None:
        raise RuntimeError(
            "tools/splat-transform/package.json does not pin an exact splat-transform version."
        )
    npx = str(probe["npx_path"])
    cmd = [npx, "--no-install", f"{SPLAT_TRANSFORM_PACKAGE}@{pinned}", *args]
    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(SPLAT_TRANSFORM_TOOL_DIR),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"splat-transform timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise RuntimeError(
            (result.stderr or "").strip()[:5000]
            or f"splat-transform exited {result.returncode}"
        )
    return result


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
    # The CLI runs from the tool directory, so pass absolute file paths.
    args = ["cleanup", str(Path(src).absolute()), str(Path(dst).absolute())]
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
    args = ["compress", str(Path(src).absolute()), str(Path(dst).absolute())]
    if format and format != "spz":
        args += ["--format", format]
    if quality is not None:
        args += ["--quality", str(quality)]
    return _run_splat_transform(args)