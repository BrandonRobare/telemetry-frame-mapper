from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_system_resources_returns_fields(client):
    with patch("backend.routers.system.psutil") as mock_psutil:
        mock_psutil.cpu_percent.return_value = 42.5
        mock_psutil.virtual_memory.return_value = MagicMock(used=4e9, total=16e9)
        mock_psutil.disk_usage.return_value = MagicMock(used=100e9, total=500e9)
        mock_psutil.disk_io_counters.return_value = None
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    data = resp.json()
    assert "cpu_pct" in data
    assert "ram_used_gb" in data
    assert "ram_total_gb" in data
    assert "disk_used_gb" in data
    assert "disk_total_gb" in data
    assert "gpu_pct" in data
    assert "vram_used_gb" in data


def test_system_resources_reports_tools_unavailable(client):
    with (
        patch("backend.routers.system.shutil.which", return_value=None),
        patch("backend.routers.system.importlib.util.find_spec", return_value=None),
    ):
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["colmap_available"] is False
    assert body["gsplat_available"] is False


def test_system_resources_reports_tools_available(client):
    with (
        patch("backend.routers.system.shutil.which", return_value="C:/colmap/bin/colmap.exe"),
        patch("backend.routers.system.importlib.util.find_spec", return_value=object()),
    ):
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["colmap_available"] is True
    assert body["gsplat_available"] is True


def test_system_resources_gpu_null_without_nvidia(client):
    with patch("backend.routers.system.psutil") as mock_psutil:
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.virtual_memory.return_value = MagicMock(used=2e9, total=8e9)
        mock_psutil.disk_usage.return_value = MagicMock(used=50e9, total=200e9)
        mock_psutil.disk_io_counters.return_value = None
        with patch("backend.routers.system.pynvml", None):
            resp = client.get("/system/resources")

    assert resp.status_code == 200
    assert resp.json()["gpu_pct"] is None
    assert resp.json()["vram_used_gb"] is None
