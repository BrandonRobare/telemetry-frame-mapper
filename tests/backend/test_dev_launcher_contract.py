"""Development-launcher contract (#803, #858, #873, #955).

The source-startup launchers are the entry point for the supported Mac
workflow. These tests pin the sync/install semantics so a future edit
cannot silently reintroduce dependency removal or lockfile mutation
without a failing gate here, and they pin that every launcher points the
Vite dev server at the backend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _commands(text: str) -> list[str]:
    """Script lines without shell (#) or batch (REM, ::) comment lines."""
    commands = []
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("#", "::")) or stripped.split(" ", 1)[0] == "rem":
            continue
        commands.append(line)
    return commands


# The exact form #803 used in dev.sh / dev.bat. cmd's `set` keeps everything up
# to `&&`, so the batch form has no space before it.
_NPM_DEV_WITH_API_URL = {
    ".sh": "VITE_API_URL=http://localhost:8000 npm run dev",
    ".bat": "set VITE_API_URL=http://localhost:8000&& npm run dev",
}


@pytest.mark.parametrize("name", ["dev.sh", "dev.bat", "run.sh", "run.bat"])
def test_launchers_point_the_frontend_at_the_backend(name):
    """Every launcher that starts the Vite dev server must hand it VITE_API_URL,
    or API calls hit the Vite SPA shell and the app renders empty. #803 fixed
    the dev launchers; #955 extends the same contract to run.sh / run.bat."""
    npm_dev = [line for line in _commands(_script(name)) if "npm run dev" in line]
    assert npm_dev, f"{name} must start the frontend dev server"
    expected = _NPM_DEV_WITH_API_URL[Path(name).suffix]
    for line in npm_dev:
        assert expected in line, f"{name} must start npm with {expected!r}: {line.strip()}"


def test_run_scripts_do_not_reinstall_or_install_frontend():
    """The run launchers must never npm-install (only the dev launchers)."""
    for name in ("run.sh", "run.bat"):
        text = _script(name)
        assert "npm install" not in text
        assert "npm ci" not in text


def test_run_sh_reaps_the_frontend_when_the_backend_dies():
    """#862: run.sh must not leave :5173 serving after the backend exits."""
    sh = _script("run.sh")
    assert "wait $BACKEND_PID" in sh
    assert "pkill -TERM -P" in sh
    assert "kill -0 \"$BACKEND_PID\"" in sh
    assert "trap cleanup EXIT" in sh