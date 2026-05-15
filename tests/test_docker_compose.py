import yaml
from pathlib import Path


def test_compose_has_nvidia_profile():
    data = yaml.safe_load(Path("docker-compose.yml").read_text())
    profiles = data["profiles"]["nvidia"]["services"]["backend"]["deploy"]
    devices = profiles["resources"]["reservations"]["devices"]
    assert any(d.get("driver") == "nvidia" for d in devices)


def test_compose_backend_default_still_works():
    data = yaml.safe_load(Path("docker-compose.yml").read_text())
    assert "backend" in data["services"]
    assert data["services"]["backend"]["build"] == "./backend"
