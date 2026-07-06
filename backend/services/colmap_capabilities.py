"""COLMAP version and capability detection.

Cached probe that runs once at import time (also callable on demand via
`probe_colmap()`) and surfaces the version string, banner, and whether
specific 4.x features are available: spatial_matcher, global_mapper,
pose_prior_mapper, and Caspar GPU bundle-adjustment backend.

The module-level dict `_CAPABILITIES` is populated lazily — import is
safe even when COLMAP is not installed (everything reads as False/None).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from functools import lru_cache

logger = logging.getLogger(__name__)

# Parsed version tuple: (major, minor, patch_string)
_VERSION_RE = re.compile(
    r"COLMAP\s+(?:(\d+)\.(\d+)(?:\.([\w.]+))?)"
    r"|(?:version\s+)?(\d+)\.(\d+)(?:\.([\w.]+))?",
    re.IGNORECASE,
)

_CAPABILITIES: dict[str, object] | None = None


def _run_colmap_help(*args: str) -> tuple[str, str] | None:
    """Return (stdout, stderr) from ``colmap <args>``, or None on failure."""
    exe = shutil.which("colmap")
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout, result.stderr
    except Exception:
        return None


def _parse_version_colmap_text(stdout: str, stderr: str) -> tuple[int, int, str] | None:
    """Extract ``(major, minor, patch_str)`` from COLMAP version / help output."""
    combined = f"{stdout}\n{stderr}"

    # COLMAP 4.x: `colmap -h` prints "COLMAP 4.1.0dev0 ..."
    m = _VERSION_RE.search(combined)
    if m:
        groups = m.groups()
        major = int(groups[0] or groups[3])
        minor = int(groups[1] or groups[4])
        patch = (groups[2] or groups[5]) or "0"
        return major, minor, patch

    # `colmap version` separate invocation
    result = _run_colmap_help("version")
    if result:
        out, err = result
        m = _VERSION_RE.search(f"{out}\n{err}")
        if m:
            groups = m.groups()
            major = int(groups[0] or groups[3])
            minor = int(groups[1] or groups[4])
            patch = (groups[2] or groups[5]) or "0"
            return major, minor, patch

    return None


def _check_subcommand(subcommand: str) -> bool:
    """Check whether ``colmap <subcommand>`` is a known subcommand."""
    result = _run_colmap_help("-h")
    if not result:
        return False
    return any(
        line.strip().startswith(subcommand)
        for line in (result[0] + result[1]).splitlines()
    )


@lru_cache(maxsize=1)
def probe_colmap() -> dict[str, object]:
    """Probe the installed COLMAP binary for version and feature flags.

    Returns a dictionary keyed by:
        available: bool  — COLMAP binary found on PATH
        version: str | None  — raw version string / banner line
        major: int | None
        minor: int | None
        patch: str | None
        is_v4: bool  — major >= 4
        features:
            spatial_matcher: bool
            global_mapper: bool
            pose_prior_mapper: bool
            caspar: bool
    """
    exe = shutil.which("colmap")
    if not exe:
        return {
            "available": False,
            "version": None,
            "major": None,
            "minor": None,
            "patch": None,
            "is_v4": False,
            "features": {
                "spatial_matcher": False,
                "global_mapper": False,
                "pose_prior_mapper": False,
                "caspar": False,
            },
        }

    # Version
    result = _run_colmap_help("-h")
    vtuple = None
    banner = None
    if result:
        out, err = result
        vtuple = _parse_version_colmap_text(out, err)
        for line in (out + err).splitlines():
            stripped = line.strip()
            if stripped and ("COLMAP" in stripped or "colmap" in stripped.lower()):
                banner = stripped[:200]
                break

    major, minor, patch = vtuple if vtuple else (None, None, None)
    is_v4 = major is not None and major >= 4

    # Feature detection
    features: dict[str, bool] = {
        "spatial_matcher": False,
        "global_mapper": False,
        "pose_prior_mapper": False,
        "caspar": False,
    }

    if exe:
        # spatial_matcher, global_mapper, pose_prior_mapper: look in subcommand help
        for subcmd, key in [
            ("spatial_matcher", "spatial_matcher"),
            ("global_mapper", "global_mapper"),
            ("pose_prior_mapper", "pose_prior_mapper"),
        ]:
            features[key] = _check_subcommand(subcmd)

        # Caspar: check bundle_adjuster --help for "BundleAdjustmentCaspar"
        ba_result = _run_colmap_help("bundle_adjuster", "--help")
        if ba_result:
            ba_text = ba_result[0] + ba_result[1]
            features["caspar"] = "BundleAdjustmentCaspar" in ba_text

    return {
        "available": True,
        "version": banner,
        "major": major,
        "minor": minor,
        "patch": patch,
        "is_v4": is_v4,
        "features": features,
    }


def get_capabilities() -> dict[str, object]:
    """Return the cached COLMAP capability probe (probes on first call)."""
    global _CAPABILITIES
    if _CAPABILITIES is None:
        _CAPABILITIES = probe_colmap()
    return _CAPABILITIES


def clear_capabilities_cache() -> None:
    """Invalidate cached capabilities so the next read re-probes."""
    global _CAPABILITIES
    _CAPABILITIES = None
    probe_colmap.cache_clear()