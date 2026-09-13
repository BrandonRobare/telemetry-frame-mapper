"""Development-launcher contract (#858, #873).

The source-startup launchers are the entry point for the supported Mac
workflow. These tests pin the sync/install semantics so a future edit
cannot silently reintroduce dependency removal or lockfile mutation
without a failing gate here.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_dev_sh_uses_inexact_sync_to_preserve_optional_groups():
    """uv sync must not prune previously installed optional groups (#858)."""
    sh = _script("dev.sh")
    assert any(
        "uv sync --inexact --group backend --group dev" in line
        for line in sh.splitlines()
    ), "dev.sh must sync with --inexact to preserve optional deps"


def test_dev_bat_uses_inexact_sync_to_preserve_optional_groups():
    bat = _script("dev.bat")
    assert "--inexact" in bat, "dev.bat must sync with --inexact to preserve optional deps"


def test_dev_launchers_install_frontend_from_the_lockfile():
    """npm ci (not npm install) so dev setups never mutate the lockfile
    or resolve loose ranges (#873)."""
    for name in ("dev.sh", "dev.bat"):
        text = _script(name)
        assert "npm ci" in text, f"{name} must run npm ci"
        assert "npm install" not in text, f"{name} must not run npm install"


def test_run_scripts_do_not_reinstall_or_install_frontend():
    """The run launchers must never npm-install (only the dev launchers)."""
    for name in ("run.sh", "run.bat"):
        text = _script(name)
        assert "npm install" not in text
        assert "npm ci" not in text