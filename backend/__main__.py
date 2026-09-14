from __future__ import annotations

import atexit
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from backend.core.config import get_deployment_config


def _bundle_lock_dir() -> Path | None:
    """Per-user writable lock directory for the packaged bundle, or None when
    running from a source checkout (no single-instance guard)."""
    if not getattr(sys, "frozen", False):
        return None
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Telemetry Frame Mapper"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else home) / "Telemetry Frame Mapper"
    return home / "Telemetry Frame Mapper"


def _open_bundle_ui(deployment: dict) -> None:
    """Packaged Finder/desktop launches need a visible entry point (#833).

    - First launch: wait for the API to listen, then open the browser once.
    - Second launch while the first instance serves: open the existing UI and
      exit instead of failing to bind the port (an already-running app should
      focus its existing tab, not error silently).
    - Skip when the deployment config disables it (the CI smoke does) or when
      running from a source checkout.
    """
    if not deployment.get("auto_open_browser", True):
        return
    lock_dir = _bundle_lock_dir()
    if lock_dir is None:
        return
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / "instance.lock"
    url = f"http://{deployment['host']}:{deployment['port']}"

    def _serving() -> bool:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1.5) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False

    if lock.exists():
        if _serving():
            webbrowser.open(url)
            sys.exit(0)  # focus the already-running instance
        lock.unlink(missing_ok=True)  # stale lock from a crashed run

    lock.touch()
    atexit.register(lambda: lock.unlink(missing_ok=True))

    def _open_when_ready() -> None:
        for _ in range(240):  # up to ~2 min for cold start
            if _serving():
                webbrowser.open(url)
                return
            time.sleep(0.5)

    threading.Thread(target=_open_when_ready, daemon=True).start()


def main() -> None:
    deployment = get_deployment_config()
    _open_bundle_ui(deployment)
    # Reload mode uses one API worker; BACKEND_RELOAD=1 is how the dev launchers ask for it.
    uvicorn.run(
        "backend.main:app",
        host=deployment["host"],
        port=deployment["port"],
        workers=1,
        reload=os.environ.get("BACKEND_RELOAD", "").strip() == "1",
    )


if __name__ == "__main__":
    main()