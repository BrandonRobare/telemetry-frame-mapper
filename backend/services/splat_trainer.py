"""In-process gaussian-splat training on ``gsplat.rasterization``.

This module is the real trainer behind ``_run_gsplat`` in
``backend/services/reconstruction.py``. It replaces
the phantom ``gsplat.train`` API the pipeline previously called — the installed
``gsplat`` package only provides rasterization primitives and densification
strategies; the training loop is user-written (see gsplat's
``examples/simple_trainer.py``).

Import discipline: the module top imports stdlib, numpy, and the sibling
:mod:`colmap_io` / :mod:`ply_io` modules only. ``torch``, ``gsplat``, and
``PIL`` are imported inside functions so the backend never requires them —
their absence degrades per the contracts below.

Contracts honored for the reconstruction pipeline:

- :func:`train_splats` without torch/gsplat raises ``RuntimeError`` whose
  message contains ``"COLMAP sparse cloud only"`` (the pipeline's
  graceful-degradation branch keys on that family).
- CUDA OOM is re-wrapped as ``RuntimeError`` containing the literal
  ``"CUDA out of memory"`` (mapped to a user-facing preset hint).
- ``cancel`` (a ``threading.Event``) is polled every iteration and raises
  :class:`ReconstructionCancelled`.
- ``progress_cb(step, pct)`` performs a DB UPDATE + commit per call, so calls
  are throttled to at most one per 2 wall-clock seconds and progress is mapped
  into the 40.0 -> 99.0 window (COLMAP owns 0-40).
- :func:`render_thumbnail` is best-effort and never raises.
- :func:`render_flythrough` keyframe interpolation uses :func:`smoothstep`,
  which must stay identical to the frontend preview formula
  (``frontend/src/features/splat/smoothstep.ts``).

One GPU job runs at a time (``_GPU_LOCK``): the target card has 4 GB of VRAM.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

from backend.services import colmap_io, ply_io

ProgressCallback = Callable[[str, float], None]


class ReconstructionCancelled(RuntimeError):
    """Raised when the cancel event is set during training."""


# One GPU job at a time — the target card (RTX 3050 Ti) has 4 GB of VRAM.
_GPU_LOCK = threading.Lock()

# Progress window owned by training: COLMAP reports 0-40, the UI completes at 100
# (the 99.0-100 tail covers LOD/thumbnail generation, which has no progress callbacks).
_PROGRESS_START = 40.0
_PROGRESS_END = 99.0
_PROGRESS_MIN_INTERVAL_S = 2.0

# Rendered thumbnails/flythroughs use a 60 degree vertical field of view; the
# thumbnail framing distance formula below assumes the same half-angle.
_RENDER_HALF_FOV_RAD = math.radians(30.0)

_MAX_RENDER_WIDTH = 1920
_MAX_RENDER_HEIGHT = 1080

# Per-attribute learning rates from gsplat's simple_trainer / INRIA defaults.
_LR_MEANS = 1.6e-4  # multiplied by scene_scale; exponential decay to 1% over the run
_LR_SCALES = 5e-3
_LR_QUATS = 1e-3
_LR_OPACITIES = 5e-2
_LR_SH0 = 2.5e-3
_LR_SHN = 1.25e-4

_SH_C0 = 0.2820947918  # zeroth-order spherical-harmonic basis constant


@dataclass
class TrainerConfig:
    """Hyperparameters for one training run.

    ``from_preset`` chooses the quick or full profile from the preset's
    ``iterations`` and applies any explicit per-field overrides found in the
    preset dict (config.yaml -> ``reconstruction.presets.*`` currently carries
    only ``iterations``; overrides are an escape hatch).
    """

    iterations: int
    sh_degree: int
    downscale_factor: int
    max_gaussians: int
    refine_start_iter: int
    refine_stop_iter: int
    refine_every: int = 100
    reset_every: int = 3000
    eval_every: int = 1000
    eval_views: int = 4
    ssim_lambda: float = 0.2
    init_opacity: float = 0.1
    # +1 SH degree per this many iterations (standard 3DGS warmup).
    sh_warmup_every: int = 1000

    @classmethod
    def from_preset(cls, preset_cfg: dict) -> TrainerConfig:
        iterations = int(preset_cfg.get("iterations", 1000))
        if iterations < 5000:
            # quick: 4000x3000 sources -> 1000x750; reset_every disabled because
            # opacity resets destabilize ultra-short runs; barely densifies by design.
            config = cls(
                iterations=iterations,
                sh_degree=1,
                downscale_factor=4,
                max_gaussians=350_000,
                refine_start_iter=300,
                refine_stop_iter=800,
                reset_every=iterations + 1,
                eval_every=250,
                sh_warmup_every=500,
            )
        else:
            # full: ~0.46 GB params+Adam at 1M gaussians / SH degree 2; the
            # viewer renders at most degree 2, so degree 3 would waste memory.
            config = cls(
                iterations=iterations,
                sh_degree=2,
                downscale_factor=2,
                max_gaussians=1_000_000,
                refine_start_iter=500,
                refine_stop_iter=15_000,
                reset_every=3000,
                eval_every=1000,
                sh_warmup_every=1000,
            )
        for field in fields(cls):
            if field.name != "iterations" and field.name in preset_cfg:
                setattr(config, field.name, type(getattr(config, field.name))(
                    preset_cfg[field.name]
                ))
        return config


def smoothstep(t: float) -> float:
    """Smoothstep easing for flythrough keyframe interpolation.

    Cross-implementation contract: must stay identical to the in-browser
    preview formula in ``frontend/src/features/splat/smoothstep.ts``.
    """
    return t * t * (3.0 - 2.0 * t)


def _import_training_deps():
    """Import torch + gsplat, or raise the pipeline's graceful-degradation error."""
    try:
        import gsplat  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Gaussian-splat training dependencies (torch + gsplat) are not installed — "
            "see docs/SETUP.md for the GPU install. "
            "The reconstruction will complete with COLMAP sparse cloud only."
        ) from exc
    return torch, gsplat


class _ProgressThrottle:
    """Wrap progress_cb so DB writes happen at most once per interval."""

    def __init__(self, cb: ProgressCallback, min_interval_s: float = _PROGRESS_MIN_INTERVAL_S):
        self._cb = cb
        self._interval = min_interval_s
        self._last = -math.inf

    def __call__(self, step: str, pct: float, *, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last >= self._interval:
            self._last = now
            self._cb(step, pct)


def _training_pct(step: int, iterations: int) -> float:
    frac = min(1.0, max(0.0, step / max(1, iterations)))
    return _PROGRESS_START + (_PROGRESS_END - _PROGRESS_START) * frac


def _look_at_viewmat(eye: np.ndarray, target: np.ndarray) -> np.ndarray:
    """World->camera 4x4 with COLMAP axes (x right, y down, z forward), up = world -Y.

    The viewer is configured with ``cameraUp [0,-1,0]``; matching it here keeps
    server renders upright relative to the in-browser view.
    """
    forward = target - eye
    norm = np.linalg.norm(forward)
    if norm < 1e-12:
        forward = np.array([0.0, 0.0, 1.0])
    else:
        forward = forward / norm
    down = np.array([0.0, 1.0, 0.0])  # camera "up" is world -Y
    right = np.cross(down, forward)
    norm = np.linalg.norm(right)
    if norm < 1e-12:  # looking straight along the down axis; pick any right
        right = np.array([1.0, 0.0, 0.0])
    else:
        right = right / norm
    down = np.cross(forward, right)
    rotation = np.stack([right, down, forward])
    viewmat = np.eye(4)
    viewmat[:3, :3] = rotation
    viewmat[:3, 3] = -rotation @ eye
    return viewmat


def _render_intrinsics(width: int, height: int) -> np.ndarray:
    focal = height / (2.0 * math.tan(_RENDER_HALF_FOV_RAD))
    return np.array(
        [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]]
    )


def _rasterize_cloud(torch, gsplat, cloud, viewmat: np.ndarray, width: int, height: int,
                     device, sh_degree: int | None = None):
    """One rasterization call for a loaded GaussianCloud; returns (H, W, 3) in [0, 1]."""
    means = torch.from_numpy(np.ascontiguousarray(cloud.means)).float().to(device)
    quats = torch.from_numpy(np.ascontiguousarray(cloud.quats)).float().to(device)
    scales = torch.from_numpy(np.ascontiguousarray(cloud.scales)).float().to(device)
    opacities = torch.from_numpy(np.ascontiguousarray(cloud.opacities)).float().to(device)
    sh0 = torch.from_numpy(np.ascontiguousarray(cloud.sh0)).float().to(device)[:, None, :]
    if sh_degree is None:
        sh_degree = int(round(math.sqrt(cloud.shN.shape[1] + 1))) - 1
    if sh_degree > 0 and cloud.shN.shape[1] > 0:
        shn = torch.from_numpy(np.ascontiguousarray(cloud.shN)).float().to(device)
        colors = torch.cat([sh0, shn], dim=1)
    else:
        colors = sh0
        sh_degree = 0
    viewmats = torch.from_numpy(viewmat[None]).float().to(device)
    ks = torch.from_numpy(_render_intrinsics(width, height)[None]).float().to(device)
    renders, _, _ = gsplat.rasterization(
        means=means,
        quats=quats,
        scales=torch.exp(scales),
        opacities=torch.sigmoid(opacities),
        colors=colors,
        viewmats=viewmats,
        Ks=ks,
        width=width,
        height=height,
        sh_degree=sh_degree,
        packed=True,
    )
    return renders[0].clamp(0.0, 1.0)


def _gaussian_window(torch, window_size: int, sigma: float, channels: int, device, dtype):
    coords = torch.arange(window_size, device=device, dtype=dtype) - window_size // 2
    gauss = torch.exp(-(coords**2) / (2 * sigma**2))
    gauss = gauss / gauss.sum()
    window_2d = gauss[:, None] @ gauss[None, :]
    return window_2d.expand(channels, 1, window_size, window_size).contiguous()


def _ssim(torch, img1, img2, window_size: int = 11):
    """SSIM over (B, C, H, W) images in [0, 1] with an 11x11 gaussian window.

    Pure-torch so no extra dependency (torchmetrics) is needed.
    """
    nnf = torch.nn.functional
    channels = img1.shape[1]
    window = _gaussian_window(torch, window_size, 1.5, channels, img1.device, img1.dtype)
    pad = window_size // 2
    mu1 = nnf.conv2d(img1, window, padding=pad, groups=channels)
    mu2 = nnf.conv2d(img2, window, padding=pad, groups=channels)
    mu1_sq, mu2_sq, mu1_mu2 = mu1**2, mu2**2, mu1 * mu2
    sigma1_sq = nnf.conv2d(img1 * img1, window, padding=pad, groups=channels) - mu1_sq
    sigma2_sq = nnf.conv2d(img2 * img2, window, padding=pad, groups=channels) - mu2_sq
    sigma12 = nnf.conv2d(img1 * img2, window, padding=pad, groups=channels) - mu1_mu2
    c1, c2 = 0.01**2, 0.03**2
    ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
        (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    )
    return ssim_map.mean()


def _psnr(torch, render, target) -> float:
    mse = float(torch.mean((render - target) ** 2).item())
    return -10.0 * math.log10(max(mse, 1e-10))


def _initial_log_scales(torch, means):
    """log(mean distance to the 3 nearest neighbors), chunked to bound memory."""
    count = means.shape[0]
    if count < 2:
        return torch.full((count, 3), math.log(0.01), device=means.device)
    nn_dist = torch.empty(count, device=means.device)
    k = min(4, count)  # nearest k includes self at distance 0
    for start in range(0, count, 4096):
        chunk = means[start : start + 4096]
        dists = torch.cdist(chunk, means)
        knn = dists.topk(k, largest=False).values
        nn_dist[start : start + 4096] = knn[:, 1:].mean(dim=1)
    return torch.log(nn_dist.clamp_min(1e-6))[:, None].repeat(1, 3)


def _load_dataset(torch, colmap_dir: Path, model, downscale_factor: int):
    """Load training views as uint8 CPU tensors plus per-view viewmats/intrinsics.

    Images are cached as uint8 (not float32): 500 frames at 1000x750 are about
    1.1 GB of RAM as uint8 and would be 4x that as float32.
    """
    from PIL import Image

    views = []
    for image in model.images:
        camera = model.cameras[image.camera_id]
        frame_path = colmap_dir / "images" / image.name
        if not frame_path.exists():
            raise RuntimeError(f"Training frame not found: {frame_path}")
        with Image.open(frame_path) as img:
            img = img.convert("RGB")
            new_size = (
                max(1, round(img.width / downscale_factor)),
                max(1, round(img.height / downscale_factor)),
            )
            if new_size != img.size:
                img = img.resize(new_size, Image.LANCZOS)
            pixels = torch.from_numpy(np.asarray(img, dtype=np.uint8))

        if camera.model == "PINHOLE":
            fx, fy, cx, cy = (float(v) for v in camera.params)
        else:  # SIMPLE_PINHOLE — colmap_io only loads distortion-free models
            fx = fy = float(camera.params[0])
            cx, cy = float(camera.params[1]), float(camera.params[2])
        scale_x = new_size[0] / camera.width
        scale_y = new_size[1] / camera.height
        intrinsics = np.array(
            [
                [fx * scale_x, 0.0, cx * scale_x],
                [0.0, fy * scale_y, cy * scale_y],
                [0.0, 0.0, 1.0],
            ]
        )
        views.append(
            {
                "pixels": pixels,  # uint8 CPU (H, W, 3)
                "viewmat": colmap_io.world_to_cam_matrix(image),
                "intrinsics": intrinsics,
                "width": new_size[0],
                "height": new_size[1],
            }
        )
    return views


def _scene_scale_from_cameras(model) -> float:
    centers = []
    for image in model.images:
        rotation = colmap_io.qvec_to_rotmat(image.qvec)
        centers.append(-rotation.T @ np.asarray(image.tvec, dtype=np.float64))
    centers = np.stack(centers)
    centroid = centers.mean(axis=0)
    return 1.1 * float(np.linalg.norm(centers - centroid, axis=1).max() or 1.0)


def train_splats(
    colmap_dir: Path,
    output_path: Path,
    config: TrainerConfig,
    progress_cb: ProgressCallback,
    cancel: threading.Event,
) -> dict:
    """Train a gaussian splat from a finished COLMAP workspace and export a PLY.

    Returns ``{gaussian_count, psnr, ssim, training_metrics}`` where
    ``training_metrics`` is ``list[{iter, psnr, ssim}] | None``. PSNR/SSIM are
    measured on training views: at drone-survey frame counts a holdout split
    would cost reconstruction quality, so there is no eval split.
    """
    torch, gsplat = _import_training_deps()
    oom_type = getattr(torch.cuda, "OutOfMemoryError", None)
    with _GPU_LOCK:
        try:
            return _train(torch, gsplat, colmap_dir, output_path, config, progress_cb, cancel)
        except Exception as exc:
            if oom_type is not None and isinstance(exc, oom_type):
                raise RuntimeError(f"CUDA out of memory: {exc}") from exc
            raise
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


def _train(
    torch,
    gsplat,
    colmap_dir: Path,
    output_path: Path,
    config: TrainerConfig,
    progress_cb: ProgressCallback,
    cancel: threading.Event,
) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    progress = _ProgressThrottle(progress_cb)
    progress("loading COLMAP model", _PROGRESS_START, force=True)

    model = colmap_io.read_model(colmap_dir / "sparse" / "0")
    if not model.images:
        raise RuntimeError("COLMAP model contains no registered images")
    if model.points_xyz.shape[0] == 0:
        raise RuntimeError("COLMAP model contains no sparse points")

    views = _load_dataset(torch, colmap_dir, model, config.downscale_factor)
    scene_scale = _scene_scale_from_cameras(model)

    # --- Parameter initialization from the sparse cloud -----------------------
    num_rest = (config.sh_degree + 1) ** 2 - 1
    means_init = torch.from_numpy(model.points_xyz.astype(np.float32)).to(device)
    rgb = torch.from_numpy(model.points_rgb.astype(np.float32)).to(device) / 255.0
    params = torch.nn.ParameterDict(
        {
            "means": torch.nn.Parameter(means_init.clone()),
            "scales": torch.nn.Parameter(_initial_log_scales(torch, means_init)),
            "quats": torch.nn.Parameter(
                torch.tensor([1.0, 0.0, 0.0, 0.0], device=device).repeat(means_init.shape[0], 1)
            ),
            "opacities": torch.nn.Parameter(
                torch.full(
                    (means_init.shape[0],),
                    math.log(config.init_opacity / (1.0 - config.init_opacity)),
                    device=device,
                )
            ),
            "sh0": torch.nn.Parameter(((rgb - 0.5) / _SH_C0)[:, None, :].clone()),
            "shN": torch.nn.Parameter(
                torch.zeros(means_init.shape[0], num_rest, 3, device=device)
            ),
        }
    )

    learning_rates = {
        "means": _LR_MEANS * scene_scale,
        "scales": _LR_SCALES,
        "quats": _LR_QUATS,
        "opacities": _LR_OPACITIES,
        "sh0": _LR_SH0,
        "shN": _LR_SHN,
    }
    optimizers = {
        name: torch.optim.Adam(
            [{"params": params[name], "lr": learning_rates[name], "name": name}], eps=1e-15
        )
        for name in params
    }
    means_scheduler = torch.optim.lr_scheduler.ExponentialLR(
        optimizers["means"], gamma=0.01 ** (1.0 / config.iterations)
    )

    strategy = gsplat.DefaultStrategy(
        refine_start_iter=config.refine_start_iter,
        refine_stop_iter=config.refine_stop_iter,
        refine_every=config.refine_every,
        reset_every=config.reset_every,
        verbose=False,
    )
    strategy.check_sanity(params, optimizers)
    state = strategy.initialize_state(scene_scale=scene_scale)

    metrics: list[dict] = []
    rng = np.random.default_rng(seed=0)
    cap_reported = False

    for step in range(config.iterations):
        if cancel.is_set():
            raise ReconstructionCancelled("Cancelled by user")

        view = views[int(rng.integers(len(views)))]
        target = view["pixels"].to(device).float() / 255.0
        viewmats = torch.from_numpy(view["viewmat"][None]).float().to(device)
        ks = torch.from_numpy(view["intrinsics"][None]).float().to(device)
        active_sh = min(step // max(1, config.sh_warmup_every), config.sh_degree)

        renders, _, info = gsplat.rasterization(
            means=params["means"],
            quats=params["quats"],
            scales=torch.exp(params["scales"]),
            opacities=torch.sigmoid(params["opacities"]),
            colors=torch.cat([params["sh0"], params["shN"]], dim=1),
            viewmats=viewmats,
            Ks=ks,
            width=view["width"],
            height=view["height"],
            sh_degree=active_sh,
            packed=True,  # packed mode saves memory on sparse aerial scenes
        )
        render = renders[0]
        l1_loss = (render - target).abs().mean()
        ssim_value = _ssim(
            torch, render.permute(2, 0, 1)[None], target.permute(2, 0, 1)[None]
        )
        loss = (1.0 - config.ssim_lambda) * l1_loss + config.ssim_lambda * (1.0 - ssim_value)

        strategy.step_pre_backward(params, optimizers, state, step, info)
        loss.backward()
        strategy.step_post_backward(params, optimizers, state, step, info, packed=True)
        for optimizer in optimizers.values():
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
        means_scheduler.step()

        # VRAM cap: freeze densification once the gaussian budget is reached.
        if (
            not cap_reported
            and params["means"].shape[0] >= config.max_gaussians
            and strategy.refine_stop_iter > step
        ):
            strategy.refine_stop_iter = step
            cap_reported = True
            progress(
                f"gaussian cap reached ({config.max_gaussians:,}) — densification frozen",
                _training_pct(step + 1, config.iterations),
                force=True,
            )

        if (step + 1) % config.eval_every == 0 or step + 1 == config.iterations:
            psnr_value, ssim_eval = _evaluate(torch, gsplat, params, views, config, device)
            metrics.append({"iter": step + 1, "psnr": psnr_value, "ssim": ssim_eval})

        progress(
            f"training {step + 1}/{config.iterations}",
            _training_pct(step + 1, config.iterations),
        )

    progress("exporting splat PLY", _PROGRESS_END, force=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cloud = ply_io.GaussianCloud(
        means=params["means"].detach().cpu().numpy().astype(np.float32),
        sh0=params["sh0"].detach().cpu().numpy()[:, 0, :].astype(np.float32),
        shN=params["shN"].detach().cpu().numpy().astype(np.float32),
        opacities=params["opacities"].detach().cpu().numpy().astype(np.float32),
        scales=params["scales"].detach().cpu().numpy().astype(np.float32),
        quats=params["quats"].detach().cpu().numpy().astype(np.float32),
    )
    ply_io.write_3dgs_ply(output_path, cloud)

    final = metrics[-1] if metrics else {"psnr": None, "ssim": None}
    return {
        "gaussian_count": int(cloud.means.shape[0]),
        "psnr": final["psnr"],
        "ssim": final["ssim"],
        "training_metrics": metrics or None,
    }


def _evaluate(torch, gsplat, params, views, config: TrainerConfig, device) -> tuple[float, float]:
    """Render evenly spaced training views under no_grad; return mean (PSNR, SSIM)."""
    indices = np.unique(
        np.linspace(0, len(views) - 1, min(config.eval_views, len(views))).astype(int)
    )
    psnrs: list[float] = []
    ssims: list[float] = []
    with torch.no_grad():
        for index in indices:
            view = views[int(index)]
            target = view["pixels"].to(device).float() / 255.0
            renders, _, _ = gsplat.rasterization(
                means=params["means"],
                quats=params["quats"],
                scales=torch.exp(params["scales"]),
                opacities=torch.sigmoid(params["opacities"]),
                colors=torch.cat([params["sh0"], params["shN"]], dim=1),
                viewmats=torch.from_numpy(view["viewmat"][None]).float().to(device),
                Ks=torch.from_numpy(view["intrinsics"][None]).float().to(device),
                width=view["width"],
                height=view["height"],
                sh_degree=config.sh_degree,
                packed=True,
            )
            render = renders[0].clamp(0.0, 1.0)
            psnrs.append(_psnr(torch, render, target))
            ssims.append(
                float(
                    _ssim(
                        torch, render.permute(2, 0, 1)[None], target.permute(2, 0, 1)[None]
                    ).item()
                )
            )
    return float(np.mean(psnrs)), float(np.mean(ssims))


def render_thumbnail(
    splat_path: Path, out_path: Path, width: int = 512, height: int = 512, quality: int = 85
) -> Path | None:
    """Best-effort nadir-ish thumbnail of a splat PLY. Never raises.

    Returns None when torch/gsplat are unavailable, the GPU is busy
    (non-blocking lock acquire), or rendering fails for any reason.
    """
    try:
        torch, gsplat = _import_training_deps()
    except RuntimeError:
        return None
    if not _GPU_LOCK.acquire(timeout=0):
        return None
    try:
        from PIL import Image

        device = "cuda" if torch.cuda.is_available() else "cpu"
        cloud = ply_io.read_3dgs_ply(splat_path)

        # Frame the central mass of the scene, not stray fliers.
        low = np.percentile(cloud.means, 5, axis=0)
        high = np.percentile(cloud.means, 95, axis=0)
        center = (low + high) / 2.0
        core = cloud.means[
            np.all((cloud.means >= low) & (cloud.means <= high), axis=1)
        ]
        if core.shape[0] < 3:
            core = cloud.means

        # Ground normal from PCA: smallest-eigenvalue eigenvector, signed toward
        # world -Y to match the viewer's cameraUp [0,-1,0].
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov(core.T.astype(np.float64)))
        normal = eigenvectors[:, 0]
        if normal[1] > 0:
            normal = -normal
        planar_axes = eigenvectors[:, 1:]
        projected = (core - center) @ planar_axes
        planar_extent = float(projected.max(axis=0).max() - projected.min(axis=0).min())
        distance = 1.4 * max(planar_extent, 1e-3) / (2.0 * math.tan(_RENDER_HALF_FOV_RAD))
        eye = center + normal * distance

        viewmat = _look_at_viewmat(eye, center)
        with torch.no_grad():
            render = _rasterize_cloud(
                torch, gsplat, cloud, viewmat, width, height, device, sh_degree=0
            )
        pixels = (render.cpu().numpy() * 255.0).astype(np.uint8)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(pixels).save(out_path, format="JPEG", quality=quality)
        return out_path
    except Exception:
        return None
    finally:
        _GPU_LOCK.release()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def render_flythrough(
    splat_path: Path,
    output_path: Path,
    keyframes: list[dict],
    *,
    fps: int,
    width: int,
    height: int,
) -> Path:
    """Render a keyframed flythrough MP4 by piping raw frames into ffmpeg.

    Keyframe position/target are interpolated with :func:`smoothstep` so the
    exported video matches the in-browser preview exactly.
    """
    try:
        torch, gsplat = _import_training_deps()
    except RuntimeError as exc:
        raise RuntimeError(
            "gsplat video rendering is not installed. Use browser recording or install "
            "optional reconstruction dependencies."
        ) from exc
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg is required for server-side flythrough rendering but was not found on "
            "PATH. Install ffmpeg (see docs/INSTALL.md) or use browser recording instead."
        )
    if len(keyframes) < 2:
        raise RuntimeError("Flythrough rendering needs at least two keyframes")

    width = min(int(width), _MAX_RENDER_WIDTH)
    height = min(int(height), _MAX_RENDER_HEIGHT)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    with _GPU_LOCK:
        try:
            cloud = ply_io.read_3dgs_ply(splat_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                "ffmpeg", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
                "-r", str(fps), "-i", "-",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(output_path),
            ]
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                with torch.no_grad():
                    for segment in range(len(keyframes) - 1):
                        current, nxt = keyframes[segment], keyframes[segment + 1]
                        # The duration belongs to the segment that travels TO the
                        # next keyframe — mirrors the frontend preview player.
                        frame_count = max(1, round(float(nxt["duration_s"]) * fps))
                        for frame in range(frame_count):
                            ease = smoothstep(frame / frame_count)
                            eye = np.array(
                                [
                                    a + (b - a) * ease
                                    for a, b in zip(
                                        current["position"], nxt["position"], strict=True
                                    )
                                ]
                            )
                            target = np.array(
                                [
                                    a + (b - a) * ease
                                    for a, b in zip(
                                        current["target"], nxt["target"], strict=True
                                    )
                                ]
                            )
                            render = _rasterize_cloud(
                                torch, gsplat, cloud, _look_at_viewmat(eye, target),
                                width, height, device,
                            )
                            pixels = (render.cpu().numpy() * 255.0).astype(np.uint8)
                            process.stdin.write(pixels.tobytes())
                    last = keyframes[-1]
                    render = _rasterize_cloud(
                        torch, gsplat, cloud,
                        _look_at_viewmat(
                            np.array(last["position"], dtype=np.float64),
                            np.array(last["target"], dtype=np.float64),
                        ),
                        width, height, device,
                    )
                    process.stdin.write(
                        (render.cpu().numpy() * 255.0).astype(np.uint8).tobytes()
                    )
            finally:
                if process.stdin is not None:
                    process.stdin.close()
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            if process.wait() != 0:
                raise RuntimeError(f"ffmpeg failed while encoding the flythrough: {stderr}")
            if not output_path.exists():
                raise RuntimeError("ffmpeg reported success but produced no output file")
            return output_path
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
