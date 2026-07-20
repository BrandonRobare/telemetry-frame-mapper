from __future__ import annotations

import os

from backend.core.config import get_config, get_deployment_config
from backend.main import app, processed_dir


def test_processed_dir_resolves_via_config():
    assert processed_dir == os.path.abspath(get_config().processed_dir)


def test_cors_uses_deployment_profile():
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs["allow_origins"] == get_deployment_config()["cors_origins"]
