"""Real-binary COLMAP option-parser compatibility (#856).

Runs only where a COLMAP 4.x binary is installed (Homebrew on macOS, system
packages elsewhere). These exercises invoke the actual installed binary the
way ``_run_colmap`` does, guarding the option-namespace regression that
mocked-argv unit tests cannot catch: option parsing is the exact boundary
that failed with ``unrecognised option`` on COLMAP 4.1.1.

Version probes are cached, so these tests add at most two subprocess calls
on machines with COLMAP and zero elsewhere.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from backend.services.colmap_capabilities import get_capabilities

_REJECTION_MARKERS = ("unrecognised", "unknown option", "unknown command")


def _colmap_v4_available() -> bool:
    caps = get_capabilities()
    return bool(caps.get("available")) and bool(caps.get("is_v4"))


def _parse_rejected(output: str) -> bool:
    lowered = output.lower()
    return any(marker in lowered for marker in _REJECTION_MARKERS)


def test_v4_binary_accepts_guided_and_global_option_namespaces(tmp_path: Path) -> None:
    if not _colmap_v4_available():
        pytest.skip("COLMAP 4.x not installed on this machine")

    exe = shutil.which("colmap")
    assert exe is not None
    db = tmp_path / "database.db"
    sqlite3.connect(db).close()

    # Guided matching: the 4.x namespace must parse; the pre-4 namespace must
    # be rejected with an option error (not proceed).
    guided_v4 = subprocess.run(
        [exe, "exhaustive_matcher", "--database_path", str(db),
         "--FeatureMatching.guided_matching=1"],
        capture_output=True, text=True, timeout=30,
    )
    guided_legacy = subprocess.run(
        [exe, "exhaustive_matcher", "--database_path", str(db),
         "--SiftMatching.guided_matching=1"],
        capture_output=True, text=True, timeout=30,
    )
    assert not _parse_rejected(guided_v4.stderr + guided_v4.stdout)
    assert _parse_rejected(guided_legacy.stderr + guided_legacy.stdout)

    # The map-related option must parse in the accepted global namespace and
    # be rejected under the incremental one, mirroring the real invocation.
    missing_images = tmp_path / "missing-images"
    global_v4 = subprocess.run(
        [exe, "global_mapper", "--database_path", str(db),
         "--image_path", str(missing_images), "--output_path", str(tmp_path / "sparse"),
         "--GlobalMapper.num_threads=2"],
        capture_output=True, text=True, timeout=30,
    )
    global_legacy = subprocess.run(
        [exe, "global_mapper", "--database_path", str(db),
         "--image_path", str(missing_images), "--output_path", str(tmp_path / "sparse"),
         "--Mapper.num_threads=2"],
        capture_output=True, text=True, timeout=30,
    )
    assert not _parse_rejected(global_v4.stderr + global_v4.stdout), global_v4.stderr
    assert _parse_rejected(global_legacy.stderr + global_legacy.stdout), global_legacy.stderr