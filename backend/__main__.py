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


def _check_reconstruction_capabilities() -> int:
    """`--check-reconstruction-deps`: exercises the reconstruction export path's
    actual capabilities in the packaged bundle, not just importability.

    A bare `import rasterio` succeeds even with no GDAL/PROJ data bundled --
    rasterio only reads that data lazily on first CRS or driver use, which is
    exactly the failure mode a v3.0.0 Windows release shipped with. This does
    the cheap, in-memory version of what the exports actually do: resolve an
    EPSG code through PROJ and round-trip a tiny GeoTIFF through a GDAL driver
    (as backend/services/orthomosaic_export.py does), then write a LAZ point
    cloud through the lazrs native backend (as
    backend/services/reconstruction.py's LAZ export does).
    """
    import io

    failures: list[str] = []
    try:
        import numpy as np
        import rasterio  # noqa: F401  (import itself is not the point here)
        from rasterio.crs import CRS
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin

        wkt = CRS.from_epsg(4326).to_wkt()  # needs PROJ's proj.db
        if not wkt:
            raise RuntimeError("CRS.from_epsg(4326).to_wkt() returned empty")
        profile = {
            "driver": "GTiff",
            "height": 1,
            "width": 1,
            "count": 1,
            "dtype": "uint8",
            "crs": CRS.from_epsg(4326),
            "transform": from_origin(0, 1, 1, 1),
        }
        with MemoryFile() as memfile:  # needs GDAL's GTiff driver + data
            with memfile.open(**profile) as dataset:
                dataset.write(np.zeros((1, 1), dtype=np.uint8), 1)
            with memfile.open() as dataset:
                dataset.read(1)
    except Exception as exc:
        failures.append(f"rasterio (PROJ/GDAL): {exc}")

    try:
        import laspy
        import numpy as np

        header = laspy.LasHeader(point_format=3, version="1.4")
        las = laspy.LasData(header)
        las.x = np.array([0.0])
        las.y = np.array([0.0])
        las.z = np.array([0.0])
        buffer = io.BytesIO()
        las.write(buffer, laz_backend=laspy.LazBackend.Lazrs)  # needs the lazrs native backend
        if not buffer.getvalue():
            raise RuntimeError("LAZ write produced no bytes")
    except Exception as exc:
        failures.append(f"laspy (lazrs): {exc}")

    if failures:
        print("reconstruction capability check failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("reconstruction capability check ok: rasterio (PROJ+GDAL), laspy (lazrs)")
    return 0


def main() -> None:
    if "--check-reconstruction-deps" in sys.argv[1:]:
        sys.exit(_check_reconstruction_capabilities())
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