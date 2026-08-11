from __future__ import annotations

import pytest

from backend.core.config import get_deployment_config
from backend.services.share_links import hash_password


def test_environment_bind_is_rejected_without_authentication(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("deployment:\n  host: 127.0.0.1\n")
    monkeypatch.setenv("DEPLOYMENT_HOST", "0.0.0.0")

    with pytest.raises(ValueError, match="not loopback but no authentication"):
        get_deployment_config(str(path))


def test_environment_bind_is_allowed_with_pin_lock(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "deployment:\n  host: 127.0.0.1\n"
        "pin_lock:\n  enabled: true\n  pin_hash_env: TEST_PIN_HASH\n"
    )
    monkeypatch.setenv("DEPLOYMENT_HOST", "0.0.0.0")
    monkeypatch.setenv("TEST_PIN_HASH", hash_password("1234"))

    assert get_deployment_config(str(path))["host"] == "0.0.0.0"
