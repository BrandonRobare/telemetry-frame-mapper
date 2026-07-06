from __future__ import annotations

from unittest.mock import MagicMock, patch


def _missing_tools(*names: str):
    return lambda name: f"/usr/bin/{name}" if name not in names else None


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
    assert "gpu_name" in data
    assert "tools" in data
    assert "workflows" in data


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
    assert {tool["key"] for tool in body["tools"]} == {
        "ffmpeg",
        "exiftool",
        "colmap",
        "torch",
        "gsplat",
        "sugar",
        "transformers",
    }
    assert body["workflows"][0]["available"] is False


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


def test_system_resources_reports_versions_and_workflows(client):
    def fake_run(args, **kwargs):
        assert kwargs["timeout"] == 2
        exe = args[0]
        return MagicMock(stdout=f"{exe} version 1.2.3\nCopyright", stderr="")

    with (
        patch("backend.routers.system.shutil.which", side_effect=_missing_tools("exiftool")),
        patch("backend.routers.system.subprocess.run", side_effect=fake_run),
        patch("backend.routers.system.importlib.util.find_spec", return_value=None),
        patch("backend.routers.system._gpu_status", return_value={
            "available": False,
            "name": None,
            "gpu_pct": None,
            "vram_used_gb": None,
            "vram_total_gb": None,
        }),
    ):
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    body = resp.json()
    tools = {tool["key"]: tool for tool in body["tools"]}
    assert tools["ffmpeg"]["available"] is True
    assert tools["ffmpeg"]["version"] == "/usr/bin/ffmpeg version 1.2.3"
    assert tools["exiftool"]["available"] is False
    assert tools["exiftool"]["install_commands"]["ubuntu"]
    workflows = {workflow["key"]: workflow for workflow in body["workflows"]}
    assert workflows["video_geotagging"]["available"] is False
    assert workflows["video_geotagging"]["missing"] == ["exiftool"]
    assert workflows["colmap_reconstruction"]["available"] is True


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
