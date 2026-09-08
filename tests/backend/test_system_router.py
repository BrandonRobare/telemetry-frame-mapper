from __future__ import annotations

from types import SimpleNamespace
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
    backend = SimpleNamespace(is_available=MagicMock(return_value=False))
    with (
        patch("backend.routers.system.shutil.which", return_value=None),
        patch("backend.routers.system.importlib.util.find_spec", return_value=None),
        patch("backend.routers.system.get_training_backend", return_value=backend),
        patch(
            "backend.routers.system.accelerator.detect",
            return_value=SimpleNamespace(kind="cpu", device="cpu"),
        ),
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
        "msplat",
        "sugar",
        "transformers",
    }
    assert body["workflows"][0]["available"] is False


def test_system_resources_reports_tools_available(client):
    backend = SimpleNamespace(is_available=MagicMock(return_value=True))
    with (
        patch("backend.routers.system.shutil.which", return_value="C:/colmap/bin/colmap.exe"),
        patch("backend.routers.system.importlib.util.find_spec", return_value=object()),
        patch("backend.routers.system.get_training_backend", return_value=backend),
        patch(
            "backend.routers.system.accelerator.detect",
            return_value=SimpleNamespace(kind="cuda", device="cuda"),
        ),
    ):
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    body = resp.json()
    assert body["colmap_available"] is True
    assert body["gsplat_available"] is True
    backend.is_available.assert_called_once_with()


def test_system_resources_reports_installed_but_unusable_gsplat_with_reason(client):
    backend = SimpleNamespace(is_available=MagicMock(return_value=False))

    def fake_spec(name: str):
        if name == "gsplat":
            return SimpleNamespace(origin="/venv/gsplat/__init__.py")
        return None

    with (
        patch("backend.routers.system.shutil.which", return_value=None),
        patch("backend.routers.system.importlib.util.find_spec", side_effect=fake_spec),
        patch("backend.routers.system.get_training_backend", return_value=backend),
        patch(
            "backend.routers.system.accelerator.detect",
            return_value=SimpleNamespace(kind="cuda", device="cuda"),
        ),
    ):
        resp = client.get("/system/resources")

    assert resp.status_code == 200
    body = resp.json()
    tools = {tool["key"]: tool for tool in body["tools"]}
    assert body["gsplat_available"] is False
    assert tools["gsplat"]["available"] is False
    assert tools["gsplat"]["path"] == "/venv/gsplat/__init__.py"
    assert "no compatible CUDA accelerator" in tools["gsplat"]["error"]
    workflows = {workflow["key"]: workflow for workflow in body["workflows"]}
    assert workflows["gaussian_splat_training"]["available"] is False
    assert "gsplat" in workflows["gaussian_splat_training"]["missing"]
    backend.is_available.assert_called_once_with()


def test_system_resources_enables_native_metal_training_without_torch(client):
    backend = SimpleNamespace(is_available=MagicMock(return_value=True))

    def fake_spec(name: str):
        if name == "msplat":
            return SimpleNamespace(origin="/venv/msplat/__init__.py")
        return None

    with (
        patch("backend.routers.system.shutil.which", return_value="/opt/homebrew/bin/colmap"),
        patch("backend.routers.system.importlib.util.find_spec", side_effect=fake_spec),
        patch("backend.routers.system.get_training_backend", return_value=backend),
        patch(
            "backend.routers.system.accelerator.detect",
            return_value=SimpleNamespace(kind="metal", device="mps"),
        ),
    ):
        response = client.get("/system/resources")

    assert response.status_code == 200
    body = response.json()
    tools = {tool["key"]: tool for tool in body["tools"]}
    workflows = {workflow["key"]: workflow for workflow in body["workflows"]}
    assert tools["msplat"]["available"] is True
    assert tools["msplat"]["path"] == "/venv/msplat/__init__.py"
    assert tools["gsplat"]["available"] is False
    assert workflows["gaussian_splat_training"] == {
        "key": "gaussian_splat_training",
        "label": "Gaussian splat training",
        "available": True,
        "missing": [],
    }
    assert body["msplat_available"] is True
    assert body["gsplat_available"] is True
    assert body["splat_backend"] == "metal_msplat"
    backend.is_available.assert_called_once_with()


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


def test_gpu_workflows_do_not_require_pynvml():
    """A usable CUDA GPU must not be gated on optional telemetry.

    pynvml is what supplies live utilisation/VRAM, and it was undeclared, so
    _gpu_status() reported available=False on every install. That flag was ANDed
    into all three GPU workflows, and the frontend disables the "Compute semantic
    labels" button from the semantic_labeling flag — making Semantic Splats (#331)
    unreachable from the UI even on a working CUDA machine.
    """
    from backend.routers.system import _workflow_statuses

    binaries = {k: {"available": True} for k in ("ffmpeg", "exiftool", "colmap")}
    python_deps = {
        "torch": {"available": True, "cuda_available": True},
        "gsplat": {"available": True},
        "sugar": {"available": True},
        "transformers": {"available": True},
    }
    no_pynvml = {"available": False, "name": None}

    workflows = {w["key"]: w for w in _workflow_statuses(binaries, python_deps, no_pynvml)}

    for key in ("gaussian_splat_training", "sugar_refinement", "semantic_labeling"):
        assert workflows[key]["available"] is True, f"{key} gated on pynvml"
        assert "nvidia_gpu" not in workflows[key]["missing"]


def test_gpu_workflows_still_report_missing_without_cuda():
    """With no CUDA device, nvidia_gpu must still be reported missing."""
    from backend.routers.system import _workflow_statuses

    binaries = {k: {"available": True} for k in ("ffmpeg", "exiftool", "colmap")}
    python_deps = {
        "torch": {"available": True, "cuda_available": False},
        "gsplat": {"available": True},
        "sugar": {"available": True},
        "transformers": {"available": True},
    }
    no_pynvml = {"available": False, "name": None}

    workflows = {w["key"]: w for w in _workflow_statuses(binaries, python_deps, no_pynvml)}

    assert workflows["gaussian_splat_training"]["available"] is False
    assert "nvidia_gpu" in workflows["gaussian_splat_training"]["missing"]
