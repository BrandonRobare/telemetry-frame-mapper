from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from backend.services.splat_backends.base import TrainerConfig
from scripts import benchmark_heldout_parity as parity


def _bundle(path: Path, run: dict, *, corrupt: bool = False) -> None:
    run = {**run}
    run.setdefault("splat_sha256", hashlib.sha256(b"ply\n").hexdigest())
    files = {
        "run.json": (json.dumps(run, sort_keys=True) + "\n").encode(),
        "splat.ply": b"ply\n",
        "environment.txt": b"platform=test\n",
        "backend.log": b"per-tile overflow\n",
    }
    sums = (
        "\n".join(
            f"{hashlib.sha256(value).hexdigest()}  {name}" for name, value in sorted(files.items())
        )
        + "\n"
    )
    with tarfile.open(path, "w:gz") as archive:
        for name, value in {**files, "SHA256SUMS": sums.encode()}.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(
                info, io.BytesIO(value if not corrupt or name != "splat.ply" else b"bad!")
            )


def test_benchmark_policy_is_exact_and_fingerprinted() -> None:
    config = parity.benchmark_config()

    assert config.iterations == 1250
    assert config.refine_stop_iter == 625
    assert config.eval_every == 0
    assert config.benchmark_heldout_split is True
    assert config.benchmark_test_every == 8
    assert config.benchmark_keep_crs is True
    assert config.background_color == (0.6130, 0.0101, 0.3984)
    assert (
        parity.policy_fingerprint()
        == hashlib.sha256(parity._canonical(parity.POLICY).encode("ascii")).hexdigest()
    )


def test_worker_subprocess_uses_module_mode_from_repository_root(tmp_path: Path) -> None:
    command, cwd = parity._worker_command(
        "metal", tmp_path / "colmap", tmp_path / "evidence", tmp_path / "result.json"
    )

    assert command[1:3] == ["-m", "scripts.benchmark_heldout_parity"]
    assert cwd == Path(parity.__file__).parents[1]


def test_export_validation_rejects_nonfinite_gaussians(tmp_path: Path) -> None:
    from backend.services import ply_io

    cloud = ply_io.GaussianCloud(
        means=np.array([[0.0, 0.0, 1.0], [np.nan, 0.0, 2.0]], dtype=np.float32),
        sh0=np.zeros((2, 3), dtype=np.float32),
        shN=np.zeros((2, 3, 3), dtype=np.float32),
        opacities=np.zeros(2, dtype=np.float32),
        scales=np.zeros((2, 3), dtype=np.float32),
        quats=np.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
    )
    output = ply_io.write_3dgs_ply(tmp_path / "invalid.ply", cloud)

    with pytest.raises(RuntimeError, match="1/2 non-finite or invalid Gaussians"):
        parity.validate_exported_splat(output, 2)


def test_fixture_metadata_has_preregistered_split_counts() -> None:
    _, fixture = parity.load_fixture()

    assert fixture["registered_view_count"] == 75
    assert fixture["sparse_point_count"] == 10883
    assert fixture["split"]["heldout_view_count"] == 10
    assert fixture["split"]["train_view_count"] == 65
    assert fixture["split"]["heldout_view_names"] == [
        "DSC00229.JPG",
        "DSC00238.JPG",
        "DSC00247.JPG",
        "DSC00257.JPG",
        "DSC00267.JPG",
        "DSC00277.JPG",
        "DSC00285.JPG",
        "DSC00293.JPG",
        "DSC00301.JPG",
        "DSC00309.JPG",
    ]


def test_committed_sparse_archive_matches_preregistered_model_tree(tmp_path: Path) -> None:
    from backend.services import colmap_io

    root, fixture = parity.load_fixture()
    parity.safe_extract(root / "aukerman-colmap-sparse.tar.gz", tmp_path)
    sparse_model = colmap_io._pick_best_submodel(tmp_path / "sparse")

    assert parity._tree_sha256(sparse_model) == fixture["sparse_model_sha256"]


def test_safe_extract_rejects_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "traversal.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))

    with pytest.raises(RuntimeError, match="unsafe archive member"):
        parity.safe_extract(archive, tmp_path / "out")


def test_bundle_validation_rejects_checksum_tampering(tmp_path: Path) -> None:
    bundle = tmp_path / "bad.tar.gz"
    _bundle(bundle, {"schema_version": 1}, corrupt=True)

    with pytest.raises(RuntimeError, match="bundle checksum mismatch"):
        parity._read_bundle(bundle)


def test_bundle_validation_rejects_absolute_path_metadata(tmp_path: Path) -> None:
    bundle = tmp_path / "absolute.tar.gz"
    _bundle(bundle, {"schema_version": 1, "bad": "/private/location"})

    with pytest.raises(RuntimeError, match="absolute path"):
        parity._read_bundle(bundle)


def test_bundle_validation_rejects_run_json_ply_identity_drift(tmp_path: Path) -> None:
    bundle = tmp_path / "wrong-ply-identity.tar.gz"
    _bundle(bundle, {"schema_version": 1, "splat_sha256": "0" * 64})

    with pytest.raises(RuntimeError, match="run.json splat checksum mismatch"):
        parity._read_bundle(bundle)


def test_protocol_metadata_rejects_policy_fixture_and_sync_drift() -> None:
    _, fixture = parity.load_fixture()
    valid = {
        "schema_version": 1,
        "kind": "cuda",
        "fixture": fixture,
        "policy": parity.POLICY,
        "policy_fingerprint": parity.policy_fingerprint(),
        "git_commit": "commit",
        "sync_confirmation": True,
        "gaussian_count": 1,
        "wall_seconds": 1.0,
        "splat_sha256": "a" * 64,
    }
    parity.validate_run_metadata(valid, "cuda", fixture, "commit")
    for key, value in (
        ("sync_confirmation", False),
        ("policy_fingerprint", "bad"),
        ("kind", "metal"),
    ):
        changed = dict(valid)
        changed[key] = value
        with pytest.raises(RuntimeError, match="invalid cuda run metadata"):
            parity.validate_run_metadata(changed, "cuda", fixture, "commit")


def test_worker_syncs_after_train_before_it_reports_result(monkeypatch, tmp_path: Path) -> None:
    backend = SimpleNamespace(is_available=lambda: True)
    order: list[str] = []

    def train(*_args):
        order.append("train")
        (tmp_path / "out" / "splat.ply").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "out" / "splat.ply").write_bytes(b"ply")
        return {"gaussian_count": 4}

    backend.train = train
    monkeypatch.setattr(
        "backend.services.splat_backends.get_training_backend", lambda kind: backend
    )
    monkeypatch.setattr(parity, "_sync_target", lambda kind: order.append("sync"))
    monkeypatch.setattr(
        parity,
        "validate_exported_splat",
        lambda path, count: order.append("validate"),
    )

    assert parity.worker("cuda", tmp_path, tmp_path / "out", tmp_path / "result.json") == 0
    assert order == ["train", "sync", "validate"]
    assert json.loads((tmp_path / "result.json").read_text())["sync_confirmation"] is True


def test_compare_verdict_and_count_alert(monkeypatch, tmp_path: Path) -> None:
    _, fixture = parity.load_fixture()
    run = {
        "schema_version": 1,
        "fixture": fixture,
        "policy": parity.POLICY,
        "policy_fingerprint": parity.policy_fingerprint(),
        "git_commit": "commit",
        "sync_confirmation": True,
        "gaussian_count": 10,
        "wall_seconds": 10.0,
    }
    cuda = tmp_path / "cuda.tar.gz"
    metal = tmp_path / "metal.tar.gz"
    _bundle(cuda, {**run, "kind": "cuda"})
    _bundle(metal, {**run, "kind": "metal", "gaussian_count": 25})
    monkeypatch.setattr(parity, "_source_images", lambda source, commit: tmp_path)
    monkeypatch.setattr(parity, "validate_fixture", lambda *args: (fixture, tmp_path))
    monkeypatch.setattr(parity, "_git_commit", lambda path: "commit")
    monkeypatch.setattr(
        "backend.services.splat_backends.get_training_backend",
        lambda kind: SimpleNamespace(is_available=lambda: True),
    )
    rendered = iter(
        [
            [
                {"name": name, "psnr": 20.0, "ssim": 0.9, "render_sha256": "c"}
                for name in fixture["split"]["heldout_view_names"]
            ],
            [
                {"name": name, "psnr": 19.1, "ssim": 0.88, "render_sha256": "m"}
                for name in fixture["split"]["heldout_view_names"]
            ],
        ]
    )
    monkeypatch.setattr(parity, "_render_bundle", lambda *args: next(rendered))

    result = parity.compare(cuda, metal, tmp_path, tmp_path / "comparison.json")

    assert result["verdict"] == "PASS"
    assert result["count_alert"] is True
    assert result["deltas"] == pytest.approx({"psnr": -0.9, "ssim": -0.02})
    assert result["timing"]["metal_to_cuda_wall_ratio"] == 1.0
    assert result["timing"]["metal_to_cuda_throughput_ratio"] == 1.0
    assert json.loads((tmp_path / "comparison.json").read_text())["verdict"] == "PASS"


def test_cuda_config_defaults_and_benchmark_background_are_opt_in() -> None:
    default = TrainerConfig.from_preset({"iterations": 1000})
    benchmark = TrainerConfig.from_preset({**parity.POLICY})

    assert default.benchmark_heldout_split is False
    assert default.benchmark_keep_crs is False
    assert default.background_color is None
    assert benchmark.benchmark_heldout_split is True
    assert benchmark.benchmark_keep_crs is True
    assert benchmark.background_color == (0.6130, 0.0101, 0.3984)


def test_cuda_split_sorts_only_benchmark_views_and_preserves_default_order(tmp_path: Path) -> None:
    from backend.services.splat_backends import cuda_gsplat

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    for name in ("a.JPG", "b.JPG", "c.JPG"):
        Image.new("RGB", (4, 4)).save(images_dir / name)
    camera = SimpleNamespace(model="PINHOLE", params=np.array([4, 4, 2, 2]), width=4, height=4)
    model = SimpleNamespace(
        cameras={1: camera},
        images=[
            SimpleNamespace(name="b.JPG", camera_id=1),
            SimpleNamespace(name="a.JPG", camera_id=1),
            SimpleNamespace(name="c.JPG", camera_id=1),
        ],
    )
    torch = SimpleNamespace(from_numpy=lambda value: value)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cuda_gsplat.colmap_io, "world_to_cam_matrix", lambda image: np.eye(4))
    try:
        default = cuda_gsplat._load_dataset(torch, tmp_path, model, 1)
        benchmark = cuda_gsplat._load_dataset(
            torch, tmp_path, model, 1, benchmark_heldout_split=True, benchmark_test_every=2
        )
    finally:
        monkeypatch.undo()

    assert len(default) == 3  # model order remains the product default
    assert len(benchmark) == 1  # sorted a,b,c; hold out a,c


def test_hardware_workflow_is_manual_branch_gated_and_version_pinned() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "heldout-parity-metal:" in workflow
    assert "heldout-parity-cuda:" in workflow
    assert workflow.count("github.event_name == 'workflow_dispatch'") >= 3
    assert workflow.count("refs/heads/wave8/784-cuda-metal-parity") >= 4
    assert "runs-on: [self-hosted, linux, x64, cuda]" in workflow
    assert "torch==2.6.0" in workflow
    assert "gsplat==1.5.3" in workflow
    assert 'version("msplat") == "1.1.4"' in workflow
    assert "gsplat.rasterization(**kwargs)" in workflow
