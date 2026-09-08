from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_cuda_usability_requires_device_and_compiled_extension() -> None:
    from backend.services.splat_backends.cuda_gsplat import _probe_cuda_runtime

    available_cuda = SimpleNamespace(is_available=lambda: True)
    unavailable_cuda = SimpleNamespace(is_available=lambda: False)
    compiled = SimpleNamespace(_C=object())
    disabled = SimpleNamespace(_C=None)

    assert _probe_cuda_runtime(SimpleNamespace(cuda=available_cuda), compiled) is True
    assert _probe_cuda_runtime(SimpleNamespace(cuda=unavailable_cuda), compiled) is False
    assert _probe_cuda_runtime(SimpleNamespace(cuda=available_cuda), disabled) is False


def test_cuda_usability_probe_is_cached_and_fails_closed(monkeypatch) -> None:
    from backend.services.splat_backends import cuda_gsplat

    calls: list[None] = []
    runtime = (
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
        SimpleNamespace(_C=object()),
    )

    def load_runtime():
        calls.append(None)
        return runtime

    monkeypatch.setattr(cuda_gsplat, "_load_cuda_runtime", load_runtime)
    cuda_gsplat.is_available.cache_clear()
    assert cuda_gsplat.is_available() is True
    assert cuda_gsplat.is_available() is True
    assert len(calls) == 1

    monkeypatch.setattr(cuda_gsplat, "_load_cuda_runtime", MagicMock(side_effect=ImportError))
    cuda_gsplat.is_available.cache_clear()
    assert cuda_gsplat.is_available() is False


def test_cuda_backend_delegates_the_complete_training_contract(monkeypatch, tmp_path: Path) -> None:
    from backend.services.splat_backends import cuda_gsplat
    from backend.services.splat_backends.base import TrainerConfig

    expected = {"gaussian_count": 7, "psnr": 21.5, "ssim": 0.8, "training_metrics": None}
    train = MagicMock(return_value=expected)
    monkeypatch.setattr(cuda_gsplat, "train_splats", train)
    config = TrainerConfig.from_preset({"iterations": 1000})
    progress = MagicMock()
    cancel = threading.Event()
    colmap_dir = tmp_path / "colmap"
    output_path = tmp_path / "splat.ply"

    result = cuda_gsplat.CUDA_GSPLAT_BACKEND.train(
        colmap_dir, output_path, config, progress, cancel
    )

    assert result == expected
    train.assert_called_once_with(colmap_dir, output_path, config, progress, cancel)


def test_backend_protocol_has_only_training_boundary_responsibilities() -> None:
    from backend.services.splat_backends.base import SplatTrainerBackend

    public_methods = {name for name in vars(SplatTrainerBackend) if not name.startswith("_")}
    assert public_methods == {"is_available", "train"}


def test_unknown_backend_override_is_rejected() -> None:
    from backend.services.splat_backends import get_training_backend

    with pytest.raises(ValueError, match="Unsupported splat trainer backend"):
        get_training_backend("metal")


def test_reconstruction_delegates_the_complete_training_boundary(monkeypatch, tmp_path) -> None:
    from backend.services import reconstruction

    expected = {"gaussian_count": 11, "psnr": 22.0, "ssim": 0.81, "training_metrics": []}
    backend = SimpleNamespace(is_available=lambda: True, train=MagicMock(return_value=expected))
    monkeypatch.setattr(reconstruction, "get_training_backend", lambda: backend)
    progress = MagicMock()
    cancel = threading.Event()
    colmap_dir = tmp_path / "colmap"
    output_path = tmp_path / "splat.ply"

    result = reconstruction._run_gsplat(
        colmap_dir,
        output_path,
        {"iterations": 1000, "max_gaussians": 1234},
        progress,
        cancel,
    )

    assert result == expected
    args = backend.train.call_args.args
    assert args[:2] == (colmap_dir, output_path)
    assert args[2].iterations == 1000
    assert args[2].max_gaussians == 1234
    assert args[3:] == (progress, cancel)


def test_reconstruction_rejects_unusable_backend_before_progress_or_training(
    monkeypatch, tmp_path
) -> None:
    from backend.services import reconstruction

    backend = SimpleNamespace(is_available=lambda: False, train=MagicMock())
    monkeypatch.setattr(reconstruction, "get_training_backend", lambda: backend)
    progress = MagicMock()

    with pytest.raises(RuntimeError, match="no compatible CUDA accelerator"):
        reconstruction._run_gsplat(
            tmp_path / "colmap",
            tmp_path / "splat.ply",
            {"iterations": 1000},
            progress,
            threading.Event(),
        )

    backend.train.assert_not_called()
    progress.assert_not_called()


def test_thumbnail_returns_none_before_importing_unusable_renderer(monkeypatch, tmp_path) -> None:
    from backend.services import splat_backends, splat_trainer

    backend = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setattr(splat_backends, "get_renderer_backend", lambda: backend)
    import_deps = MagicMock(side_effect=AssertionError("renderer dependencies must not import"))
    monkeypatch.setattr(splat_trainer, "_import_training_deps", import_deps)

    assert splat_trainer.render_thumbnail(tmp_path / "input.ply", tmp_path / "out.jpg") is None
    import_deps.assert_not_called()


def test_flythrough_names_accelerator_and_browser_fallback_before_import(
    monkeypatch, tmp_path
) -> None:
    from backend.services import splat_backends, splat_trainer

    backend = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setattr(splat_backends, "get_renderer_backend", lambda: backend)
    import_deps = MagicMock(side_effect=AssertionError("renderer dependencies must not import"))
    monkeypatch.setattr(splat_trainer, "_import_training_deps", import_deps)

    with pytest.raises(
        RuntimeError,
        match="no compatible CUDA accelerator.*Use browser recording",
    ):
        splat_trainer.render_flythrough(
            tmp_path / "input.ply",
            tmp_path / "out.mp4",
            [{"position": [0, 0, 0]}, {"position": [1, 1, 1]}],
            fps=30,
            width=1280,
            height=720,
        )

    import_deps.assert_not_called()


def test_renderer_protocol_is_narrow_and_backend_neutral() -> None:
    from backend.services.splat_backends.base import SplatRendererBackend

    public_methods = {name for name in vars(SplatRendererBackend) if not name.startswith("_")}
    assert public_methods == {"is_available", "rasterize"}


def test_cuda_renderer_preserves_flythrough_sh_degree_derivation(monkeypatch) -> None:
    from backend.services.splat_backends import cuda_gsplat

    rasterize = MagicMock(return_value="render")
    monkeypatch.setattr(cuda_gsplat, "_import_training_deps", lambda: ("torch", "gsplat"))
    monkeypatch.setattr(cuda_gsplat, "_rasterize_cloud", rasterize)

    result = cuda_gsplat.CUDA_GSPLAT_RENDERER_BACKEND.rasterize(
        "torch", "cloud", "view", 1280, 720, "cuda"
    )

    assert result == "render"
    assert rasterize.call_args.kwargs["sh_degree"] is None


def test_cuda_renderer_preserves_expected_depth_gsplat_contract(monkeypatch) -> None:
    from backend.services.splat_backends import cuda_gsplat

    tensor = MagicMock()
    tensor.float.return_value = tensor
    tensor.to.return_value = tensor
    depth = MagicMock()
    renders = MagicMock()
    renders.__getitem__.return_value = depth
    torch = MagicMock(float32="float32")
    torch.from_numpy.return_value = tensor
    torch.zeros.return_value = tensor
    torch.exp.return_value = tensor
    torch.sigmoid.return_value = tensor
    gsplat = MagicMock()
    gsplat.rasterization.return_value = (renders, None, None)
    monkeypatch.setattr(cuda_gsplat, "_import_training_deps", lambda: (torch, gsplat))
    cloud = SimpleNamespace(
        means=MagicMock(__len__=lambda _self: 1),
        quats="quats",
        scales="scales",
        opacities="opacities",
    )
    viewmat = MagicMock()
    intrinsics = MagicMock()

    result = cuda_gsplat.CUDA_GSPLAT_RENDERER_BACKEND.rasterize(
        torch,
        cloud,
        viewmat,
        640,
        480,
        "cpu",
        sh_degree=0,
        intrinsics=intrinsics,
        render_mode="ED",
        packed=True,
    )

    assert result is depth
    kwargs = gsplat.rasterization.call_args.kwargs
    assert kwargs["render_mode"] == "ED"
    assert kwargs["sh_degree"] == 0
    assert kwargs["packed"] is True
    assert kwargs["width"] == 640
    assert kwargs["height"] == 480
