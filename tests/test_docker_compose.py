from pathlib import Path

import yaml

COMPOSE_FILE = Path(__file__).parent.parent / "docker-compose.yml"


def test_compose_has_nvidia_gpu_config():
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    deploy = data["services"]["backend"]["deploy"]
    devices = deploy["resources"]["reservations"]["devices"]
    assert any(d.get("driver") == "nvidia" for d in devices)


def test_compose_backend_default_still_works():
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    assert "backend" in data["services"]
    assert data["services"]["backend"]["build"] == "./backend"
