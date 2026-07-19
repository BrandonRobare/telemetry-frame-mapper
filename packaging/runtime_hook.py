from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
app_data = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Telemetry Frame Mapper"
app_data.mkdir(parents=True, exist_ok=True)

config = app_data / "config.yaml"
if not config.exists():
    shutil.copyfile(bundle_root / "config.yaml", config)

for name in ("data", "imports", "processed", "exports"):
    (app_data / name).mkdir(exist_ok=True)

os.chdir(app_data)