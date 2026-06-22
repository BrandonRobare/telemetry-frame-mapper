from __future__ import annotations

import os

from backend.core.config import get_config
from backend.main import processed_dir


def test_processed_dir_resolves_via_config():
    assert processed_dir == os.path.abspath(get_config().processed_dir)
