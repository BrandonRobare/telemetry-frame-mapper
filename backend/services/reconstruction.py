from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

from shapely.geometry import Point, shape
from sqlalchemy.orm import Session as DBSession

from backend.core.config import (
    get_config,
    get_reconstruction_config,
    get_remote_worker_config,
    get_render_config,
)
from backend.core.paths import confine_path
from backend.db.database import SessionLocal
from backend.db.models import (
    Image,
    JobQueueEntry,
    Reconstruction,
    ReconstructionFrame,
    SessionComparison,
    SessionFrameSelection,
)
from backend.services import ply_io, splat_trainer
from backend.services.camera_calibration import calibration_profile_for_images
from backend.services.colmap_io import _pick_best_submodel
from backend.services.job_queue import (
    FLYTHROUGH_RENDER,
    MESH_EXPORT,
    RECONSTRUCTION,
    SESSION_COMPARISON,
    JobNonRetryableError,
    enqueue,
    mark_complete,
    register_handler,
    update_payload,
)
from backend.services.remote_worker import (
    RemoteWorkerError,
    dispatch_reconstruction,
    get_reconstruction_status,
)
from backend.services.remote_worker import cancel_reconstruction as cancel_remote_reconstruction
from backend.services.semantic_labels import (
    NUM_CLASSES,
    accumulate_votes,
    finalize_labels,
    is_sidecar_stale,
    lod_labels,
    project_to_view,
    read_sidecar,
    visibility_mask,
    write_sidecar,
)
from backend.services.semantic_segmenter import segment_frame
from backend.services.splat_trainer import ReconstructionCancelled, TrainerConfig

# Tracks the running COLMAP subprocess per reconstruction so cancel can
# terminate it immediately instead of waiting for the current step to finish.
_running_subprocess: dict[int, subprocess.Popen] = {}
_running_subprocess_lock = threading.Lock()

_rec_logs: dict[int, list[str]] = {}
_rec_logs_lock = threading.Lock()


def _kill_running_subprocess(reconstruction_id: int) -> None:
    """Terminate the running COLMAP subprocess for the reconstruction, if any."""
    with _running_subprocess_lock:
        proc = _running_subprocess.pop(reconstruction_id, None)
    if proc is None:
        return
    try:
        proc.terminate()  # TerminateProcess on Windows — sufficient for COLMAP
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass
_mesh_jobs: set[int] = set()
_mesh_jobs_lock = threading.Lock()
_flythrough_jobs: set[int] = set()
_flythrough_jobs_lock = threading.Lock()
_semantic_jobs: set[int] = set()
_semantic_jobs_lock = threading.Lock()
_semantic_cancel_events: dict[int, threading.Event] = {}
_comparison_jobs: set[int] = set()
_comparison_jobs_lock = threading.Lock()
_rec_status_condition = threading.Condition()
_rec_status_versions: dict[int, int] = {}

# Cap stored error messages to avoid bloating a DB row or JSON API response
# with a pathological multi-MB stderr dump, while still keeping enough of the
# tail to be actionable (the full log remains available via the
# /reconstruction/{id}/log endpoint).
_ERROR_MSG_MAX_CHARS = 5000

logger = logging.getLogger(__name__)

# Remote poll liveness: a single dropped poll (connection reset, read timeout)
# must not orphan an hours-long remote job.  Declare the remote dead only after
# BOTH thresholds are crossed; reset on any successful poll.
_REMOTE_POLL_MAX_CONSECUTIVE_FAILURES = 5
_REMOTE_POLL_FAILURE_WINDOW_S = 600  # 10 minutes since the last successful poll


def _log_rec(rec_id: int, msg: str) -> None:
    with _rec_logs_lock:
        buf = _rec_logs.setdefault(rec_id, [])
        buf.append(f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}")
        if len(buf) > 500:
            _rec_logs[rec_id] = buf[-500:]


def get_rec_log(rec_id: int) -> list[str]:
    with _rec_logs_lock:
        return list(_rec_logs.get(rec_id, []))


def clear_rec_logs() -> None:
    with _rec_logs_lock:
        _rec_logs.clear()


def notify_reconstruction_status_changed(rec_id: int) -> None:
    with _rec_status_condition:
        _rec_status_versions[rec_id] = _rec_status_versions.get(rec_id, 0) + 1
        _rec_status_condition.notify_all()


def current_reconstruction_status_version(rec_id: int) -> int:
    with _rec_status_condition:
        return _rec_status_versions.get(rec_id, 0)


def wait_for_reconstruction_status_change(
    rec_id: int,
    last_version: int,
    timeout_s: float = 15.0,
) -> int:
    deadline = time.monotonic() + timeout_s
    with _rec_status_condition:
        while _rec_status_versions.get(rec_id, 0) <= last_version:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return last_version
            _rec_status_condition.wait(timeout=remaining)
        return _rec_status_versions.get(rec_id, 0)


# ---------------------------------------------------------------------------
# Workspace writer
# ---------------------------------------------------------------------------

def _write_colmap_workspace(colmap_dir: Path, images: list) -> None:
    """Create COLMAP workspace directory structure and seed cameras.txt."""
    images_dir = colmap_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (colmap_dir / "sparse").mkdir(parents=True, exist_ok=True)

    cfg = get_config()
    recon_cfg = get_reconstruction_config()
    calibration = calibration_profile_for_images(
        images,
        recon_cfg.get("camera_profiles", []),
        cfg.image_width_px,
        cfg.image_height_px,
        cfg.fov_horizontal_deg,
        cfg.fov_vertical_deg,
        recon_cfg.get("camera_model", "PINHOLE"),
    )
    camera_model = calibration["suggested_colmap_camera_model"]
    width = int(calibration["width"])
    height = int(calibration["height"])
    f_px = calibration.get("focal_px") or (width / 2) / math.tan(
        math.radians(cfg.fov_horizontal_deg / 2)
    )
    cx = width / 2
    cy = height / 2
    cameras_txt = colmap_dir / "cameras.txt"
    if camera_model == "SIMPLE_PINHOLE":
        # SIMPLE_PINHOLE: 3 params — f cx cy
        params_str = f"{f_px:.4f} {cx:.4f} {cy:.4f}"
    else:
        # PINHOLE (default): 4 params — fx fy cx cy
        params_str = f"{f_px:.4f} {f_px:.4f} {cx:.4f} {cy:.4f}"
    cameras_txt.write_text(
        "# Camera list with one line of data per camera:\n"
        "#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n"
        f"1 {camera_model} {width} {height} {params_str}\n"
    )

    for img in images:
        src = Path(img.filepath)
        # Never trust the stored filename as a path fragment: a restored session bundle
        # carries it verbatim from the archive manifest, so a value like
        # "../../../config.yaml" would escape the workspace on the copy2 fallback below.
        # PureWindowsPath (not PurePath) so "/", "\" and drive letters are all stripped
        # regardless of the host OS — a POSIX server may restore a Windows-authored bundle.
        safe_name = PureWindowsPath(img.filename or "").name
        if not safe_name:
            continue
        dest = images_dir / safe_name
        if dest.exists():
            continue
        try:
            os.symlink(src.resolve(), dest)
        except (OSError, NotImplementedError):
            shutil.copy2(src, dest)


# ---------------------------------------------------------------------------
# COLMAP subprocess runner
# ---------------------------------------------------------------------------

def _colmap_matcher_command(matcher_key: str) -> tuple[str, bool]:
    """Return (COLMAP matcher subcommand, guided_matching_enabled)."""
    presets = {
        "sequential": ("sequential_matcher", False),
        "sequential_guided": ("sequential_matcher", True),
        "exhaustive": ("exhaustive_matcher", False),
        "exhaustive_guided": ("exhaustive_matcher", True),
    }
    return presets.get(matcher_key, presets["exhaustive"])


def _run_colmap(
    colmap_dir: Path,
    progress_cb,
    cancel: threading.Event,
    *,
    reconstruction_id: int | None = None,
    images_have_gps: bool = False,
    image_count: int = 0,
) -> int | None:
    """Run COLMAP feature_extractor → matcher → mapper pipeline.

    Returns the number of registered images, or None if cancelled before completion.

    When COLMAP 4.x capabilities are detected and the session has GPS data
    with at least ``spatial_matcher_min_images`` images, the spatial_matcher
    is used instead of the configured matcher (O(N·k) vs O(N²)).  The
    ``mapper`` config key selects the mapper backend: ``incremental`` (default)
    or ``global`` (GLOMAP, gated on capability).
    """
    from backend.services.colmap_capabilities import get_capabilities as _colmap_cap

    db_path = str(colmap_dir / "database.db")
    image_path = str(colmap_dir / "images")
    output_path = str(colmap_dir / "sparse")
    output_dir = Path(output_path)
    cfg = get_reconstruction_config()

    camera_model = cfg.get("camera_model", "PINHOLE")
    single_camera = "1" if cfg.get("single_camera", True) else "0"
    matcher_key = cfg.get("matcher", "exhaustive")
    mapper_key = cfg.get("mapper", "incremental")
    spatial_min = int(cfg.get("spatial_matcher_min_images", 150))

    # Resolve feature flags from capability probe
    colmap_info = _colmap_cap()
    features: dict = colmap_info.get("features", {})  # type: ignore[assignment]

    # GPS-primed spatial_matcher selection
    if (
        images_have_gps
        and image_count >= spatial_min
        and features.get("spatial_matcher")
    ):
        colmap_matcher = "spatial_matcher"
        guided_matching = False
    else:
        colmap_matcher, guided_matching = _colmap_matcher_command(matcher_key)

    matcher_cmd = ["colmap", colmap_matcher, "--database_path", db_path]
    if guided_matching:
        matcher_cmd.append("--SiftMatching.guided_matching=1")

    # Spatial matcher tuning: sane defaults for drone lawnmower surveys
    if colmap_matcher == "spatial_matcher":
        matcher_cmd += [
            "--SpatialMatching.is_gps", "1",
            "--SpatialMatching.ignore_z", "1",
            "--SpatialMatching.max_num_neighbors", "50",
            "--SpatialMatching.max_distance", "100",
        ]

    # Mapper selection: global vs incremental
    if mapper_key == "global" and features.get("global_mapper"):
        mapper_subcommand = "global_mapper"
    else:
        mapper_subcommand = "mapper"

    mapper_cmd = [
        "colmap", mapper_subcommand,
        "--database_path", db_path,
        "--image_path", image_path,
        "--output_path", output_path,
        f"--Mapper.num_threads={cfg['colmap_threads']}",
    ]

    def model_converter_cmd() -> list[str]:
        """Build the model_converter command against the actual sub-model directory.

        COLMAP's mapper writes into a numbered sub-model dir (``sparse/0``, and
        ``sparse/1`` … when the reconstruction fragments), never into ``sparse``
        itself. Pointing the converter at ``sparse`` makes it fail with "rigs,
        cameras, frames, images, points3D files do not exist", which aborts every
        run at this step.

        Resolved lazily: ``steps`` is built before the mapper has run, so the
        sub-model directory does not exist yet at that point.
        """
        submodel = _pick_best_submodel(colmap_dir / "sparse")
        return ["colmap", "model_converter",
                "--input_path", str(submodel),
                "--output_path", str(submodel),
                "--output_type", "TXT"]

    steps = [
        (
            ["colmap", "feature_extractor",
             "--database_path", db_path,
             "--image_path", image_path,
             f"--SiftExtraction.max_num_features={cfg['sift_max_features']}",
             "--ImageReader.camera_model", camera_model,
             "--ImageReader.single_camera", single_camera],
            "feature extraction",
            8.0,
        ),
        (matcher_cmd, "feature matching", 20.0),
        (mapper_cmd, "bundle adjustment", 38.0),
        (model_converter_cmd, "model conversion", 40.0),
    ]

    for cmd, step_name, pct in steps:
        if cancel.is_set():
            return None
        if callable(cmd):
            cmd = cmd()
        progress_cb(step_name, pct)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "COLMAP executable not found: colmap. Install COLMAP and ensure it is on PATH "
                "before starting reconstruction."
            ) from exc
        if reconstruction_id is not None:
            with _running_subprocess_lock:
                _running_subprocess[reconstruction_id] = proc
        try:
            _, stderr = proc.communicate()
        finally:
            if reconstruction_id is not None:
                with _running_subprocess_lock:
                    _running_subprocess.pop(reconstruction_id, None)
        # A killed step surfaces as cancellation, not failure: cancel is set
        # before the process is terminated (see cancel_reconstruction).
        if cancel.is_set():
            return None
        if proc.returncode != 0:
            raise RuntimeError(
                f"COLMAP {step_name} failed: {stderr[:_ERROR_MSG_MAX_CHARS]}"
            )

    best_submodel = _pick_best_submodel(output_dir)
    images_txt = best_submodel / "images.txt"
    registered_count = _count_registered_images(images_txt) if images_txt.exists() else 0
    if registered_count == 0:
        raise RuntimeError(
            "Not enough feature matches — add more overlapping frames or reduce altitude"
        )

    progress_cb("colmap complete", 40.0)
    return registered_count


def _count_registered_images(images_txt: Path) -> int:
    """Count registered images by parsing COLMAP TXT format correctly.

    Each registered image has a header line (IMAGE_ID QW QX QY QZ TX TY TZ
    CAMERA_ID NAME) spanning at least 10 tokens. Images registered with zero
    2D points have an empty second line, which the old line-count//2 heuristic
    miscounts. Instead we count header lines whose first token is a valid int.
    """
    count = 0
    for line in images_txt.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 10:
            try:
                int(parts[0])
                count += 1
            except ValueError:
                pass
    return count


def _registered_image_names(colmap_dir: Path) -> set[str]:
    """Return image filenames present in the best COLMAP sub-model."""
    images_txt = _pick_best_submodel(colmap_dir / "sparse") / "images.txt"
    if not images_txt.exists():
        return set()
    names: set[str] = set()
    for line in images_txt.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#") or line.startswith(" "):
            continue
        parts = line.split()
        if len(parts) >= 10:
            names.add(parts[9])
    return names


def build_reconstruction_diagnostics(db: DBSession, rec: Reconstruction) -> dict:
    """Build post-COLMAP diagnostics for registered/unregistered frames."""
    frames = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == rec.id
    ).all()
    image_ids = [frame.image_id for frame in frames]
    images = []
    if image_ids:
        images = (
            db.query(Image)
            .filter(Image.id.in_(image_ids))
            .order_by(Image.timestamp, Image.id)
            .all()
        )
    frame_by_image_id = {frame.image_id: frame for frame in frames}
    registered_names = _registered_image_names(Path(rec.colmap_dir)) if rec.colmap_dir else set()

    def image_payload(img: Image, registered: bool) -> dict:
        frame = frame_by_image_id.get(img.id)
        return {
            "id": img.id,
            "filename": img.filename,
            "timestamp": img.timestamp.isoformat() if img.timestamp else None,
            "latitude": img.latitude,
            "longitude": img.longitude,
            "altitude_m": img.altitude_m,
            "colmap_error_px": frame.colmap_error_px if frame else None,
            "registered": registered,
        }

    registered = [image_payload(img, True) for img in images if img.filename in registered_names]
    unregistered = [
        image_payload(img, False) for img in images if img.filename not in registered_names
    ]
    total = len(images)
    registered_count = len(registered)
    unregistered_count = len(unregistered)
    registration_pct = (registered_count / total * 100.0) if total else 0.0

    timeline = []
    bucket_count = min(12, max(1, total))
    if total:
        for bucket_idx in range(bucket_count):
            start = math.floor(bucket_idx * total / bucket_count)
            end = math.floor((bucket_idx + 1) * total / bucket_count)
            chunk = images[start:end]
            unreg = [img for img in chunk if img.filename not in registered_names]
            timeline.append({
                "bucket": bucket_idx,
                "start_index": start,
                "end_index": max(start, end - 1),
                "total": len(chunk),
                "unregistered": len(unreg),
                "unregistered_pct": (len(unreg) / len(chunk) * 100.0) if chunk else 0.0,
            })

    map_heatmap = [
        {
            "id": item["id"],
            "filename": item["filename"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "weight": 1,
        }
        for item in unregistered
        if item["latitude"] is not None and item["longitude"] is not None
    ]

    suggestions = []
    if total == 0:
        suggestions.append({
            "code": "no_frames",
            "title": "No frames were selected",
            "detail": "Select usable frames before starting reconstruction.",
            "setting": None,
        })
    elif registered_count == 0:
        suggestions.extend([
            {
                "code": "try_exhaustive_guided",
                "title": "Run exhaustive guided matching",
                "detail": (
                    "No images registered. Exhaustive guided matching often recovers weak "
                    "overlap at the cost of runtime."
                ),
                "setting": {"matcher": "exhaustive_guided"},
            },
            {
                "code": "more_overlap",
                "title": "Increase overlap or reduce frame stride",
                "detail": (
                    "Extract frames more frequently or fly with higher forward/side overlap "
                    "so adjacent views share more features."
                ),
                "setting": {"default_video_fps": "increase"},
            },
        ])
    elif unregistered_count:
        suggestions.append({
            "code": "retry_guided",
            "title": "Retry with guided matching",
            "detail": (
                "Some frames did not register. Guided matching can add geometrically "
                "consistent correspondences after the first match pass."
            ),
            "setting": {"matcher": "sequential_guided"},
        })
        if registration_pct < 70.0:
            suggestions.append({
                "code": "increase_features",
                "title": "Extract more SIFT features",
                "detail": (
                    "Raise SIFT max features for texture-poor or high-altitude footage, "
                    "then rerun reconstruction."
                ),
                "setting": {"sift_max_features": "increase"},
            })
        suggestions.append({
            "code": "higher_overlap",
            "title": "Use higher overlap / lower frame stride",
            "detail": (
                "Clusters of unregistered frames usually indicate insufficient overlap, "
                "motion blur, or abrupt viewpoint changes."
            ),
            "setting": {"frame_stride": "reduce"},
        })
    else:
        suggestions.append({
            "code": "all_registered",
            "title": "All selected frames registered",
            "detail": "No matching changes are suggested for this run.",
            "setting": None,
        })

    return {
        "reconstruction_id": rec.id,
        "summary": {
            "frames_used": total,
            "registered_count": registered_count,
            "unregistered_count": unregistered_count,
            "registration_pct": registration_pct,
            "matcher": get_reconstruction_config().get("matcher", "exhaustive"),
        },
        "registered_images": registered,
        "unregistered_images": unregistered,
        "timeline_heatmap": timeline,
        "map_heatmap": map_heatmap,
        "suggestions": suggestions,
    }


def plan_dense_rerun(db: DBSession, rec: Reconstruction) -> dict:
    """Find weak source-frame spans and a denser, viable child selection.

    COLMAP's per-frame error is the only registration evidence used here.  A
    null error means the frame was not registered *only when at least one
    source frame has a parsed error*, avoiding guesses from incomplete output.
    """
    if rec.source_session_ids:
        raise ValueError("Dense rerun currently supports single-session reconstructions only")
    if rec.status != "complete":
        raise ValueError("Reconstruction must be complete before planning a dense rerun")

    cfg = get_reconstruction_config().get("dense_rerun", {})
    min_run = max(1, int(cfg.get("min_weak_run_frames", 2)))
    error_threshold = float(cfg.get("high_reprojection_error_px", 2.0))
    context = max(0, int(cfg.get("context_frames", 1)))

    source_frames = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == rec.id
    ).all()
    source_ids = {frame.image_id for frame in source_frames}
    if not source_ids:
        raise ValueError("Reconstruction has no recorded source frames")
    frame_by_id = {frame.image_id: frame for frame in source_frames}
    if not any(frame.colmap_error_px is not None for frame in source_frames):
        raise ValueError("Per-frame reprojection data is unavailable; cannot identify weak areas")

    images = db.query(Image).filter(
        Image.session_id == rec.session_id
    ).order_by(Image.timestamp, Image.id).all()
    source_images = [image for image in images if image.id in source_ids]
    if len(source_images) != len(source_ids):
        raise ValueError("Some source frames are no longer available in the session")

    weak_runs: list[list[Image]] = []
    current: list[Image] = []
    for image in source_images:
        error = frame_by_id[image.id].colmap_error_px
        weak = error is None or error >= error_threshold
        if weak:
            current.append(image)
        elif current:
            if len(current) >= min_run:
                weak_runs.append(current)
            current = []
    if len(current) >= min_run:
        weak_runs.append(current)
    if not weak_runs:
        raise ValueError("No weak registration span meets the configured rerun threshold")

    index_by_id = {image.id: index for index, image in enumerate(images)}
    rerun_ids = set(source_ids)
    spans = []
    for run in weak_runs:
        start = max(0, index_by_id[run[0].id] - context)
        end = min(len(images), index_by_id[run[-1].id] + context + 1)
        added = [
            image.id for image in images[start:end] if image.usable and image.id not in source_ids
        ]
        rerun_ids.update(added)
        spans.append({
            "source_image_ids": [image.id for image in run],
            "candidate_image_ids": [image.id for image in images[start:end] if image.usable],
            "added_image_ids": added,
            "start_image_id": run[0].id,
            "end_image_id": run[-1].id,
        })
    if len(rerun_ids) == len(source_ids):
        raise ValueError("Weak areas have no additional usable frames for a denser rerun")

    return {
        "reconstruction_id": rec.id,
        "preset": rec.preset,
        "thresholds": {
            "min_weak_run_frames": min_run,
            "high_reprojection_error_px": error_threshold,
            "context_frames": context,
        },
        "source_image_ids": [image.id for image in source_images],
        "rerun_image_ids": [image.id for image in images if image.id in rerun_ids],
        "added_image_ids": [image.id for image in images if image.id in rerun_ids - source_ids],
        "weak_spans": spans,
    }


def _store_reprojection_errors(db: DBSession, reconstruction_id: int, colmap_dir: Path) -> None:
    """Read COLMAP TXT output and write per-frame mean reprojection error to DB."""
    best = _pick_best_submodel(colmap_dir / "sparse")
    points3d_txt = best / "points3D.txt"
    images_txt = best / "images.txt"
    if not points3d_txt.exists() or not images_txt.exists():
        return

    # Build {point3d_id: error} from points3D.txt
    errors: dict[int, float] = {}
    for line in points3d_txt.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 8:
            errors[int(parts[0])] = float(parts[7])

    # Parse images.txt (two lines per image after comments)
    name_to_error: dict[str, float | None] = {}
    raw_lines = [line for line in images_txt.read_text().splitlines() if not line.startswith("#")]
    i = 0
    while i < len(raw_lines):
        header = raw_lines[i].strip()
        if not header:
            i += 1
            continue
        parts = header.split()
        name = parts[9]
        i += 1
        points_line = raw_lines[i].strip() if i < len(raw_lines) else ""
        i += 1
        tokens = points_line.split()
        valid = [
            errors[int(tokens[j])]
            for j in range(2, len(tokens), 3)
            if tokens[j] != "-1" and int(tokens[j]) in errors
        ]
        name_to_error[name] = sum(valid) / len(valid) if valid else None

    # Load frames and images for this reconstruction
    frames = db.query(ReconstructionFrame).filter(
        ReconstructionFrame.reconstruction_id == reconstruction_id
    ).all()
    image_ids = [f.image_id for f in frames]
    images = db.query(Image).filter(Image.id.in_(image_ids)).all()
    img_map = {img.filename: img.id for img in images}
    frame_map = {f.image_id: f for f in frames}

    for name, error in name_to_error.items():
        if name in img_map and img_map[name] in frame_map:
            frame_map[img_map[name]].colmap_error_px = error

    db.commit()


_CHECKPOINT_RE = re.compile(
    r"\[iter\s+(\d+)\]\s+PSNR:\s+([\d.]+)\s+SSIM:\s+([\d.]+)"
)


def _parse_checkpoint_metrics(output: str) -> list[dict]:
    # Retained for log-replay compatibility: the in-process trainer (T3) returns
    # metrics directly, but tests and historical training logs still use this format.
    return [
        {"iter": int(m.group(1)), "psnr": float(m.group(2)), "ssim": float(m.group(3))}
        for m in _CHECKPOINT_RE.finditer(output)
    ]


def _compute_coverage_gaps(
    splat_path: Path, reconstruction_id: int, voxel_size_m: float = 0.5
) -> tuple[list[dict], Path]:
    """Voxelize Gaussian positions from .ply and classify sparse cells.

    Returns (cells, output_path). The cache is stored next to the reconstruction
    artifact instead of under cfg.exports_dir so settings changes do not stale
    the cached path.
    """
    rec_id_segment = str(int(reconstruction_id))
    output_path = splat_path.resolve().parent / f"coverage_gaps_{rec_id_segment}.json"
    import numpy as np

    data = splat_path.read_bytes()

    header_marker = b"\nend_header\n"
    header_end = data.index(header_marker) + len(header_marker)
    header_text = data[:header_end].decode("ascii", errors="replace")

    vertex_count = 0
    properties: list[str] = []
    is_binary_little = False
    for line in header_text.splitlines():
        if line.startswith("element vertex"):
            vertex_count = int(line.split()[-1])
        elif line.startswith("property float"):
            properties.append(line.split()[-1])
        elif "binary_little_endian" in line:
            is_binary_little = True

    if vertex_count == 0:
        return [], output_path

    body = data[header_end:]

    if is_binary_little:
        dtype = np.dtype([(p, np.float32) for p in properties])
        vertices = np.frombuffer(body[: vertex_count * dtype.itemsize], dtype=dtype)
        x = vertices["x"].astype(np.float64)
        y = vertices["y"].astype(np.float64)
        z = vertices["z"].astype(np.float64)
    else:
        rows = body.decode("ascii", errors="replace").splitlines()[:vertex_count]
        idx = {p: i for i, p in enumerate(properties)}
        arr = np.array(
            [[float(r.split()[idx["x"]]), float(r.split()[idx["y"]]),
              float(r.split()[idx["z"]])] for r in rows if r.strip()],
            dtype=np.float64,
        )
        x, y, z = arr[:, 0], arr[:, 1], arr[:, 2]

    xi = ((x - x.min()) / voxel_size_m).astype(int)
    yi = ((y - y.min()) / voxel_size_m).astype(int)
    zi = ((z - z.min()) / voxel_size_m).astype(int)

    coords = np.stack([xi, yi, zi], axis=1)
    unique_voxels, counts = np.unique(coords, axis=0, return_counts=True)

    median_count = float(np.median(counts))

    cells = []
    for (vx, vy, vz), count in zip(unique_voxels, counts, strict=True):
        ratio = count / median_count
        if ratio >= 0.40:
            continue
        if ratio < 0.05:
            level = "very_sparse"
        elif ratio < 0.25:
            level = "thin"
        else:
            level = "sparse"
        cells.append({
            "x": float(x.min() + vx * voxel_size_m),
            "y": float(y.min() + vy * voxel_size_m),
            "z": float(z.min() + vz * voxel_size_m),
            "size": voxel_size_m,
            "level": level,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cells))
    return cells, output_path


def compute_coverage_gaps(
    splat_path: Path,
    reconstruction_id: int,
    voxel_size_m: float = 0.5,
) -> tuple[list[dict], Path]:
    return _compute_coverage_gaps(
        splat_path,
        reconstruction_id,
        voxel_size_m=voxel_size_m,
    )


# Identity transform used only as the downstream default for a *non*-georeferenced
# reconstruction: it renders point sources in COLMAP's local frame and attaches no
# CRS (utm_zone "unknown" -> _utm_epsg None). It is never stored in the DB — a
# reconstruction that could not be georeferenced keeps rec.geo_transform NULL.
_LOCAL_FRAME_GEO = {
    "scale": 1.0,
    "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "translation": [0.0, 0.0, 0.0],
    "utm_zone": "unknown",
    "utm_origin": [0.0, 0.0],
}


def _extract_geo_transform(colmap_dir: Path) -> dict | None:
    """Return the persisted COLMAP->UTM transform, or None if none was solved.

    The solve (backend.services.georeferencing_solve) writes geo_transform.json
    only on success, so its absence means the reconstruction is not georeferenced.
    """
    geo_ref = colmap_dir / "geo_transform.json"
    if geo_ref.exists():
        return json.loads(geo_ref.read_text())
    return None


def _compute_geo_transform(reconstruction_id: int, colmap_dir: Path, images: list) -> dict | None:
    """Solve COLMAP-world -> UTM from camera centres and frame GPS (best effort).

    Returns the transform dict (and writes geo_transform.json) on success, or None
    when alignment is impossible/degenerate — logging the reason. Never raises.
    """
    from backend.services import georeferencing_solve

    sparse_dir = _pick_best_submodel(colmap_dir / "sparse")
    try:
        geo = georeferencing_solve.compute_geo_transform(colmap_dir, sparse_dir, images)
    except Exception as exc:  # best-effort: a solve failure must not fail the pipeline
        logger.warning("Georeferencing solve raised for reconstruction %s: %s",
                       reconstruction_id, exc)
        _log_rec(reconstruction_id, f"Georeferencing failed: {exc}")
        return None
    if geo is None:
        _log_rec(reconstruction_id, "Georeferencing: not georeferenced (alignment failed)")
    else:
        _log_rec(
            reconstruction_id,
            f"Georeferencing: aligned to UTM {geo['utm_zone']} (scale {geo['scale']:.4g})",
        )
    return geo


def _filter_images_to_target_area(images: list, geom_geojson: str) -> list:
    """Return images whose GPS position falls inside the target area polygon."""
    polygon = shape(json.loads(geom_geojson))
    return [
        img for img in images
        if img.latitude is not None and img.longitude is not None
        and Point(img.longitude, img.latitude).within(polygon)
    ]


# ---------------------------------------------------------------------------
# gsplat training (requires GPU + gsplat installed)
# ---------------------------------------------------------------------------

def _run_gsplat(
    colmap_dir: Path, output_path: Path, preset_cfg: dict, progress_cb, cancel: threading.Event
) -> dict:
    """Train a Gaussian splat. Returns {gaussian_count, psnr, ssim, training_metrics}."""
    config = TrainerConfig.from_preset(preset_cfg)
    return splat_trainer.train_splats(colmap_dir, output_path, config, progress_cb, cancel)


def _generate_lod(splat_path: Path) -> tuple[Path, Path]:
    """Return (preview_path, medium_path) — opacity-pruned variants using configured ratios."""
    render_cfg = get_render_config()
    preview_ratio = float(render_cfg.get("lod_preview_ratio", 0.10))
    medium_ratio = float(render_cfg.get("lod_medium_ratio", 0.50))
    preview = splat_path.with_name(splat_path.stem + "_preview.ply")
    medium = splat_path.with_name(splat_path.stem + "_medium.ply")
    ply_io.prune_by_opacity(splat_path, preview, keep_ratio=preview_ratio)
    ply_io.prune_by_opacity(splat_path, medium, keep_ratio=medium_ratio)
    return preview, medium


def _generate_thumbnail(splat_path: Path, out_path: Path) -> Path | None:
    """Render a JPEG thumbnail of the splat at the configured size/quality.

    Best-effort: returns out_path on success, None when the GPU stack is
    unavailable or rendering fails (the trainer never raises here)."""
    render_cfg = get_render_config()
    size = int(render_cfg.get("thumbnail_size_px", 512))
    quality = int(render_cfg.get("thumbnail_quality", 85))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return splat_trainer.render_thumbnail(splat_path, out_path, width=size, height=size,
                                          quality=quality)


def _read_colmap_points3d(points3d_txt: Path) -> tuple:
    """Return COLMAP sparse XYZ and RGB arrays from points3D.txt."""
    import numpy as np

    if not points3d_txt.exists():
        raise RuntimeError(f"COLMAP points file not found: {points3d_txt}")

    xyz: list[list[float]] = []
    rgb: list[list[int]] = []
    for line in points3d_txt.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        xyz.append([float(parts[1]), float(parts[2]), float(parts[3])])
        rgb.append([int(parts[4]), int(parts[5]), int(parts[6])])

    if not xyz:
        raise RuntimeError("COLMAP points3D.txt contains no sparse points")

    return np.array(xyz, dtype=np.float64), np.array(rgb, dtype=np.uint8)


def _ply_dtype_for(property_type: str):
    import numpy as np

    type_map = {
        "char": np.int8,
        "int8": np.int8,
        "uchar": np.uint8,
        "uint8": np.uint8,
        "short": np.int16,
        "int16": np.int16,
        "ushort": np.uint16,
        "uint16": np.uint16,
        "int": np.int32,
        "int32": np.int32,
        "uint": np.uint32,
        "uint32": np.uint32,
        "float": np.float32,
        "float32": np.float32,
        "double": np.float64,
        "float64": np.float64,
    }
    try:
        return type_map[property_type]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported PLY property type: {property_type}") from exc


def _load_ply_positions_and_colors(ply_path: Path) -> tuple:
    """Load Gaussian positions and optional RGB colors from a scalar vertex PLY."""
    import numpy as np

    data = ply_path.read_bytes()
    # Accept both Unix (\n) and Windows (\r\n) line endings in the PLY header.
    for _marker in (b"\nend_header\r\n", b"\nend_header\n"):
        try:
            header_end = data.index(_marker) + len(_marker)
            break
        except ValueError:
            continue
    else:
        raise RuntimeError("PLY end_header marker not found")
    header_text = data[:header_end].decode("ascii", errors="replace")

    vertex_count = 0
    vertex_properties: list[tuple[str, str]] = []
    in_vertex = False
    is_binary_little = False
    for line in header_text.splitlines():
        if line.startswith("format binary_little_endian"):
            is_binary_little = True
        elif line.startswith("element vertex"):
            vertex_count = int(line.split()[-1])
            in_vertex = True
        elif line.startswith("element "):
            in_vertex = False
        elif in_vertex and line.startswith("property "):
            parts = line.split()
            if parts[1] == "list":
                raise RuntimeError("PLY list properties are not supported for point cloud export")
            vertex_properties.append((parts[2], parts[1]))

    if vertex_count == 0:
        raise RuntimeError("PLY contains no vertices")

    body = data[header_end:]
    names = [name for name, _type in vertex_properties]

    if is_binary_little:
        dtype = np.dtype([
            (name, _ply_dtype_for(prop_type)) for name, prop_type in vertex_properties
        ])
        vertices = np.frombuffer(body[: vertex_count * dtype.itemsize], dtype=dtype)
        columns = {name: vertices[name] for name in names}
    else:
        rows = [
            r.split()
            for r in body.decode("ascii", errors="replace").splitlines()[:vertex_count]
        ]
        columns = {
            name: np.array([row[index] for row in rows], dtype=_ply_dtype_for(prop_type))
            for index, (name, prop_type) in enumerate(vertex_properties)
        }

    for required in ("x", "y", "z"):
        if required not in columns:
            raise RuntimeError(f"PLY is missing {required} vertex property")

    xyz = np.column_stack([columns["x"], columns["y"], columns["z"]]).astype(np.float64)

    if {"red", "green", "blue"} <= set(columns):
        rgb = np.column_stack([columns["red"], columns["green"], columns["blue"]])
        return xyz, np.clip(rgb, 0, 255).astype(np.uint8)

    if {"f_dc_0", "f_dc_1", "f_dc_2"} <= set(columns):
        sh_c0 = 0.28209479177387814
        rgb_float = 0.5 + sh_c0 * np.column_stack(
            [columns["f_dc_0"], columns["f_dc_1"], columns["f_dc_2"]]
        ).astype(np.float64)
        return xyz, np.clip(rgb_float, 0.0, 1.0) * 255.0

    return xyz, None


def _nearest_gaussian_indices(points_xyz, gaussian_xyz):
    """Return nearest Gaussian index for each point, chunked to bound memory use."""
    import numpy as np

    if len(gaussian_xyz) == 0:
        return np.full(len(points_xyz), -1, dtype=np.int64)

    indices = np.empty(len(points_xyz), dtype=np.int64)
    chunk_size = 512
    for start in range(0, len(points_xyz), chunk_size):
        stop = min(start + chunk_size, len(points_xyz))
        chunk = points_xyz[start:stop]
        distances = ((chunk[:, None, :] - gaussian_xyz[None, :, :]) ** 2).sum(axis=2)
        indices[start:stop] = np.argmin(distances, axis=1)
    return indices


def _nearest_gaussian_colors(points_xyz, gaussian_xyz, gaussian_rgb, fallback_rgb):
    """Color each COLMAP point from the nearest Gaussian, falling back to COLMAP RGB."""
    import numpy as np

    if gaussian_rgb is None or len(gaussian_xyz) == 0:
        return fallback_rgb

    nearest = _nearest_gaussian_indices(points_xyz, gaussian_xyz)
    return np.clip(gaussian_rgb[nearest], 0, 255).astype(np.uint8)


def _semantic_labels_to_asprs(
    points_xyz,
    gaussian_xyz,
    labels,
):
    """Transfer per-Gaussian project classes to ASPRS LAS classification codes."""
    import numpy as np

    mapping = np.array([2, 5, 6, 1, 9, 1], dtype=np.uint8)
    classifications = np.zeros(len(points_xyz), dtype=np.uint8)
    if len(gaussian_xyz) == 0 or len(labels) == 0:
        return classifications

    nearest = _nearest_gaussian_indices(points_xyz, gaussian_xyz)
    valid = (nearest >= 0) & (nearest < len(labels))
    source = np.asarray(labels, dtype=np.uint8)
    mapped = np.zeros(len(points_xyz), dtype=np.uint8)
    class_valid = valid & (source[nearest.clip(min=0)] < len(mapping))
    mapped[class_valid] = mapping[source[nearest[class_valid]]]
    classifications[valid] = mapped[valid]
    return classifications


def _semantic_sidecar_for_splat(splat_path: Path) -> Path:
    return splat_path.parent / "semantic_labels.npz"


def _utm_epsg(utm_zone: str) -> int | None:
    match = re.match(r"^(\d{1,2})([NS])$", utm_zone, re.IGNORECASE)
    if not match:
        return None
    zone = int(match.group(1))
    if zone < 1 or zone > 60:
        return None
    return (32600 if match.group(2).upper() == "N" else 32700) + zone


def _world_points_to_utm(points_xyz, geo: dict | None):
    import numpy as np

    if not geo or _utm_epsg(str(geo.get("utm_zone", ""))) is None:
        return points_xyz

    rotation = np.array(geo["rotation"], dtype=np.float64)
    translation = np.array(geo["translation"], dtype=np.float64)
    origin = np.array([geo["utm_origin"][0], geo["utm_origin"][1], 0.0], dtype=np.float64)
    transformed = float(geo["scale"]) * (points_xyz @ rotation.T) + translation + origin
    return transformed


def _write_las_laz(las, output_path: Path) -> None:
    """Write *las* as a LAZ-compressed file via lazrs or laszip backend.

    Raises RuntimeError if no LAZ backend is available.
    """
    import sys

    import laspy

    lazrs_spec = None
    laszip_spec = None
    if "laspy" in sys.modules:
        lazrs_spec = getattr(sys.modules["laspy"], "LazrsBackend", None)
        laszip_spec = getattr(sys.modules["laspy"], "LaszipBackend", None)

    # laspy >= 2.5 exposes compressed backends via laspy.LazrsBackend
    for backend_cls in (lazrs_spec, laszip_spec):
        if backend_cls is not None:
            try:
                las.write(str(output_path), do_compress=backend_cls)
                return
            except Exception:
                continue

    # Fallback: try the older laspy.CompressedWriter style
    try:
        writer = laspy.CompressedWriter(str(output_path), "laz", las.header)
        writer.write_points(las.points)
        writer.close()
        return
    except (AttributeError, TypeError):
        pass

    raise RuntimeError(
        "No LAZ backend available. Install laspy[lazrs] or laspy[laszip] "
        "to enable compressed point-cloud export."
    )


def _export_point_cloud(
    colmap_dir: Path,
    splat_path: Path,
    output_path: Path,
    *,
    laz_backend: bool = False,
) -> Path:
    """Export COLMAP sparse points as a colored LAS 1.4 / LAZ point cloud.

    When *laz_backend* is True and a LAZ-compatible backend (lazrs or laszip)
    is available, the output is written as a compressed LAZ file.  Falls back
    to standard LAS 1.4 when the backend is unavailable or *laz_backend* is
    False (the default).
    """
    import laspy
    import numpy as np
    from pyproj import CRS

    cfg = get_config()
    output_path = confine_path(output_path, Path(cfg.exports_dir))

    points_xyz, colmap_rgb = _read_colmap_points3d(
        _pick_best_submodel(colmap_dir / "sparse") / "points3D.txt"
    )
    gaussian_xyz, gaussian_rgb = _load_ply_positions_and_colors(splat_path)
    colors = _nearest_gaussian_colors(points_xyz, gaussian_xyz, gaussian_rgb, colmap_rgb)

    classifications = None
    semantic_sidecar = _semantic_sidecar_for_splat(splat_path)
    # A stale (older-schema / count-mismatched) sidecar holds wrong labels — treat
    # it as absent so the export is unclassified rather than misclassified (#498).
    if not is_sidecar_stale(semantic_sidecar, len(gaussian_xyz)):
        sidecar = read_sidecar(semantic_sidecar)
        classifications = _semantic_labels_to_asprs(
            points_xyz,
            gaussian_xyz,
            sidecar["labels"],
        )

    # A non-georeferenced reconstruction (no solved transform) exports in the
    # local COLMAP frame with no CRS attached — honest, not falsely georeferenced.
    geo = _extract_geo_transform(colmap_dir) or _LOCAL_FRAME_GEO
    output_xyz = _world_points_to_utm(points_xyz, geo)

    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = output_xyz.min(axis=0)
    epsg = _utm_epsg(str(geo.get("utm_zone", "")))
    if epsg is not None:
        header.add_crs(CRS.from_epsg(epsg))

    las = laspy.LasData(header)
    las.x = output_xyz[:, 0]
    las.y = output_xyz[:, 1]
    las.z = output_xyz[:, 2]
    las.red = colors[:, 0].astype(np.uint16) * 257
    las.green = colors[:, 1].astype(np.uint16) * 257
    las.blue = colors[:, 2].astype(np.uint16) * 257
    if classifications is not None:
        las.classification = classifications

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if laz_backend:
        _write_las_laz(las, output_path)
    else:
        las.write(output_path)
    return output_path



# ---------------------------------------------------------------------------
# Semantic label sidecar generation
# ---------------------------------------------------------------------------

def render_expected_depth(cloud: ply_io.GaussianCloud, view: dict, *, device: str = "cuda"):
    """Render expected depth for one COLMAP view using gsplat ED mode."""
    import gsplat
    import torch

    means = torch.from_numpy(cloud.means).float().to(device)
    quats = torch.from_numpy(cloud.quats).float().to(device)
    scales = torch.from_numpy(cloud.scales).float().to(device)
    opacities = torch.from_numpy(cloud.opacities).float().to(device)
    colors = torch.zeros((len(cloud.means), 1, 3), dtype=torch.float32, device=device)
    renders, _, _ = gsplat.rasterization(
        means=means,
        quats=quats,
        scales=torch.exp(scales),
        opacities=torch.sigmoid(opacities),
        colors=colors,
        viewmats=torch.from_numpy(view["viewmat"][None]).float().to(device),
        Ks=torch.from_numpy(view["intrinsics"][None]).float().to(device),
        width=int(view["width"]),
        height=int(view["height"]),
        render_mode="ED",
        sh_degree=0,
        packed=True,
    )
    return renders[0, ..., 0].detach().cpu().numpy()


def compute_semantic_labels(
    rec: Reconstruction,
    *,
    log_cb=None,
    cancel: threading.Event | None = None,
) -> Path:
    """Compute per-gaussian semantic labels and write semantic_labels.npz."""
    import numpy as np

    from backend.services import colmap_io

    if not rec.colmap_dir:
        raise RuntimeError("COLMAP workspace not found")
    if not rec.splat_path or not Path(rec.splat_path).exists():
        raise RuntimeError("Splat file not found on disk")
    cancel = cancel or threading.Event()
    splat_path = Path(rec.splat_path)
    colmap_dir = Path(rec.colmap_dir)
    cloud = ply_io.read_3dgs_ply(splat_path)
    model = colmap_io.read_model(_pick_best_submodel(colmap_dir / "sparse"))
    views = splat_trainer._load_dataset(__import__("torch"), colmap_dir, model, 1)
    votes = np.zeros((len(cloud.means), NUM_CLASSES), dtype=np.float32)
    with splat_trainer._GPU_LOCK:
        segmenter = None
        for index, view in enumerate(views, start=1):
            if cancel.is_set():
                raise ReconstructionCancelled("semantic labeling cancelled")
            labels_2d, _confidence = segment_frame(view["pixels"].numpy(), segmenter=segmenter)
            expected_depth = render_expected_depth(cloud, view)
            projected = project_to_view(cloud.means, view["viewmat"], view["intrinsics"])
            visible = visibility_mask(projected, expected_depth)
            accumulate_votes(votes, labels_2d, projected, visible, cloud.opacities)
            if log_cb:
                log_cb(f"Semantic labels: processed view {index}/{len(views)}")
    labels, confidence = finalize_labels(votes)
    render_cfg = get_render_config()
    labels_medium = lod_labels(
        labels,
        cloud.opacities,
        float(render_cfg.get("lod_medium_ratio", 0.5)),
    )
    labels_preview = lod_labels(
        labels,
        cloud.opacities,
        float(render_cfg.get("lod_preview_ratio", 0.1)),
    )
    out_path = write_sidecar(
        _reconstruction_export_dir(rec.id),
        labels,
        confidence,
        labels_medium,
        labels_preview,
        extra_meta={"source": "semantic_labeling"},
    )
    return out_path


def start_semantic_labeling(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise ValueError("Reconstruction not found")
    if rec.status != "complete":
        raise ValueError("Reconstruction must be complete before semantic labeling")
    if not rec.splat_path:
        raise ValueError("Splat file not found on disk")
    if rec.semantic_status in {"pending", "running"} and reconstruction_id not in _semantic_jobs:
        rec.semantic_status = None
        db.commit()
    if rec.semantic_status in {"pending", "running"}:
        raise ValueError(
            f"Semantic labeling already running for reconstruction {reconstruction_id}"
        )
    with _semantic_jobs_lock:
        if reconstruction_id in _semantic_jobs:
            raise ValueError(
            f"Semantic labeling already running for reconstruction {reconstruction_id}"
        )
        _semantic_jobs.add(reconstruction_id)
    cancel = threading.Event()
    _semantic_cancel_events[reconstruction_id] = cancel
    rec.semantic_status = "pending"
    rec.semantic_error = None
    db.commit()
    db.refresh(rec)
    threading.Thread(target=_run_semantic_job, args=(reconstruction_id,), daemon=True).start()
    return rec


def _run_semantic_job(reconstruction_id: int) -> None:
    db = SessionLocal()
    try:
        rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
        if rec is None:
            return
        rec.semantic_status = "running"
        rec.semantic_error = None
        db.commit()
        cancel = _semantic_cancel_events.get(reconstruction_id, threading.Event())
        path = compute_semantic_labels(
            rec,
            log_cb=lambda msg: _log_rec(reconstruction_id, msg),
            cancel=cancel,
        )
        rec.semantic_labels_path = str(path)
        rec.semantic_status = "complete"
        rec.semantic_error = None
        if rec.pointcloud_path:
            cached = Path(rec.pointcloud_path)
            if cached.exists():
                cached.unlink()
            rec.pointcloud_path = None
        db.commit()
    except Exception as exc:
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).update({
            "semantic_status": "failed",
            "semantic_error": str(exc)[:_ERROR_MSG_MAX_CHARS],
        })
        db.commit()
    finally:
        db.close()
        _semantic_cancel_events.pop(reconstruction_id, None)
        with _semantic_jobs_lock:
            _semantic_jobs.discard(reconstruction_id)


def semantic_overlay_bytes(rec: Reconstruction, lod: str = "preview") -> bytes:
    import struct

    import numpy as np

    if not rec.splat_path:
        raise RuntimeError("Splat file not found on disk")
    labels_path = (
        Path(rec.semantic_labels_path)
        if rec.semantic_labels_path
        else _semantic_sidecar_for_splat(Path(rec.splat_path))
    )
    if not labels_path.exists():
        raise RuntimeError("Semantic labels not found")
    cloud = ply_io.read_3dgs_ply(Path(rec.splat_path))
    # Stale sidecar (older schema / count mismatch) → treat as absent (#498).
    if is_sidecar_stale(labels_path, len(cloud.means)):
        raise RuntimeError("Semantic labels not found")
    data = read_sidecar(labels_path)
    render_cfg = get_render_config()
    if lod == "preview":
        order = ply_io.prune_order(cloud.opacities, float(render_cfg.get("lod_preview_ratio", 0.1)))
        labels = data["labels_preview"]
    elif lod == "medium":
        order = ply_io.prune_order(cloud.opacities, float(render_cfg.get("lod_medium_ratio", 0.5)))
        labels = data["labels_medium"]
    else:
        order = np.arange(len(cloud.means))
        labels = data["labels"]
    xyz = np.asarray(cloud.means[order], dtype="<f4")
    labels = np.asarray(labels, dtype=np.uint8)
    return struct.pack("<I", len(labels)) + xyz.tobytes() + labels.tobytes()

# ---------------------------------------------------------------------------
# Phase 7 exports: mesh, flythrough video, multi-session comparison
# ---------------------------------------------------------------------------

def _reconstruction_export_dir(reconstruction_id: int) -> Path:
    cfg = get_config()
    return Path(cfg.exports_dir) / str(reconstruction_id)


def _load_geo_transform_for_reconstruction(rec: Reconstruction) -> dict:
    """Return the reconstruction's UTM transform, or the local-frame default.

    Downstream point/mesh exporters always need a transform dict; a
    non-georeferenced reconstruction falls back to _LOCAL_FRAME_GEO (identity,
    no CRS) rather than None so those consumers render in the local frame.
    """
    if rec.geo_transform:
        return json.loads(rec.geo_transform)
    if rec.colmap_dir:
        return _extract_geo_transform(Path(rec.colmap_dir)) or _LOCAL_FRAME_GEO
    return _LOCAL_FRAME_GEO


def _mesh_georef_metadata(rec: Reconstruction, geo: dict) -> dict:
    return {
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
        "created_at": datetime.now(UTC).isoformat(),
        "geo_transform": geo,
    }


def _write_mesh_georef(output_dir: Path, rec: Reconstruction, geo: dict) -> Path:
    metadata = _mesh_georef_metadata(rec, geo)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "mesh_georef.json"
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def _embed_glb_extras(glb_path: Path, metadata: dict) -> bool:
    """Best-effort GLB metadata embedding; sidecar remains authoritative."""
    if not glb_path.exists():
        return False
    try:
        from pygltflib import GLTF2  # type: ignore[import]
    except ImportError:
        return False

    try:
        gltf = GLTF2().load(str(glb_path))
        extras = dict(getattr(gltf.asset, "extras", None) or {})
        extras["telemetry_frame_mapper"] = metadata
        gltf.asset.extras = extras
        gltf.save(str(glb_path))
    except Exception:
        return False
    return True


def _coerce_mesh_result_paths(result: object, output_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    if isinstance(result, dict):
        for fmt in ("glb", "obj", "mtl"):
            value = result.get(fmt) or result.get(f"{fmt}_path")
            if value:
                paths[fmt] = Path(value)
    elif isinstance(result, (list, tuple)):
        for value in result:
            path = Path(value)
            suffix = path.suffix.lower().lstrip(".")
            if suffix in {"glb", "obj", "mtl"}:
                paths[suffix] = path

    for fmt, filename in {"glb": "mesh.glb", "obj": "mesh.obj", "mtl": "mesh.mtl"}.items():
        candidate = output_dir / filename
        if fmt not in paths and candidate.exists():
            paths[fmt] = candidate

    return paths


def _run_sugar(colmap_dir: Path, splat_path: Path, output_dir: Path) -> dict[str, Path]:
    """Run SuGaR mesh export and return any generated glb/obj/mtl paths."""
    try:
        from sugar_scene import export_mesh as sugar_export_mesh  # type: ignore[import]
    except ImportError:
        try:
            from sugar import export_mesh as sugar_export_mesh  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "SuGaR is not installed. SuGaR (https://github.com/Anttwo/SuGaR) has no "
                "pip-installable release and must be installed manually by cloning that "
                "repo. Mesh export is optional; splat viewing and the rest of "
                "reconstruction work fine without it."
            ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = sugar_export_mesh(
            colmap_dir=str(colmap_dir),
            splat_path=str(splat_path),
            output_dir=str(output_dir),
            formats=("glb", "obj"),
        )
    except TypeError:
        result = sugar_export_mesh(str(colmap_dir), str(splat_path), str(output_dir))

    paths = _coerce_mesh_result_paths(result, output_dir)
    if "glb" not in paths and "obj" not in paths:
        raise RuntimeError("SuGaR mesh export did not produce a GLB or OBJ file")
    return paths


def _export_mesh_assets(rec: Reconstruction) -> dict[str, Path | None]:
    if rec.status != "complete":
        raise RuntimeError("Reconstruction must be complete before mesh export")
    if not rec.colmap_dir:
        raise RuntimeError("COLMAP workspace not found")
    if not rec.splat_path or not Path(rec.splat_path).exists():
        raise RuntimeError("Splat file not found on disk")

    output_dir = _reconstruction_export_dir(rec.id)
    geo = _load_geo_transform_for_reconstruction(rec)
    georef_path = _write_mesh_georef(output_dir, rec, geo)
    paths = _run_sugar(Path(rec.colmap_dir), Path(rec.splat_path), output_dir)
    metadata = _mesh_georef_metadata(rec, geo)
    if "glb" in paths:
        _embed_glb_extras(paths["glb"], metadata)
    return {
        "glb": paths.get("glb"),
        "obj": paths.get("obj"),
        "mtl": paths.get("mtl"),
        "georef": georef_path,
    }


def start_mesh_export(reconstruction_id: int, db: DBSession) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise ValueError("Reconstruction not found")
    if rec.status != "complete":
        raise ValueError("Reconstruction must be complete before mesh export")
    if rec.mesh_status in {"pending", "running"}:
        raise ValueError(f"Mesh export already running for reconstruction {reconstruction_id}")

    rec.mesh_status = "pending"
    rec.mesh_error = None
    db.commit()
    db.refresh(rec)

    enqueue(MESH_EXPORT, reconstruction_id, priority=5)
    return rec


def _run_mesh_export_job(entry, db, cancel: threading.Event) -> None:
    """Job queue handler for mesh export."""
    reconstruction_id = entry.target_id
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        return
    rec.mesh_status = "running"
    rec.mesh_error = None
    db.commit()

    try:
        outputs = _export_mesh_assets(rec)
        rec.mesh_glb_path = str(outputs["glb"]) if outputs["glb"] else None
        rec.mesh_obj_path = str(outputs["obj"]) if outputs["obj"] else None
        rec.mesh_mtl_path = str(outputs["mtl"]) if outputs["mtl"] else None
        rec.mesh_status = "complete"
        rec.mesh_error = None
        db.commit()
        mark_complete(entry.id)
    except Exception as exc:
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).update({
            "mesh_status": "failed",
            "mesh_error": str(exc)[:_ERROR_MSG_MAX_CHARS],
        })
        db.commit()
        raise


def _validate_keyframes(keyframes: list[dict]) -> list[dict]:
    if len(keyframes) < 2:
        raise RuntimeError("At least two keyframes are required")
    normalized = []
    for index, frame in enumerate(keyframes):
        position = frame.get("position")
        target = frame.get("target", [0.0, 0.0, 0.0])
        duration_s = float(frame.get("duration_s", 3.0))
        if not isinstance(position, list) or len(position) != 3:
            raise RuntimeError(f"Keyframe {index} position must contain three numbers")
        if not isinstance(target, list) or len(target) != 3:
            raise RuntimeError(f"Keyframe {index} target must contain three numbers")
        if duration_s <= 0:
            raise RuntimeError(f"Keyframe {index} duration_s must be positive")
        normalized.append({
            "position": [float(v) for v in position],
            "target": [float(v) for v in target],
            "duration_s": duration_s,
        })
    return normalized


def _run_video_renderer(
    splat_path: Path,
    output_path: Path,
    keyframes: list[dict],
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Render an offline flythrough video when browser recording is unavailable."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    splat_trainer.render_flythrough(
        splat_path, output_path, keyframes, fps=fps, width=width, height=height
    )
    if not output_path.exists():
        raise RuntimeError("Video renderer did not write an output file")
    return output_path


def start_flythrough_render(
    reconstruction_id: int,
    db: DBSession,
    keyframes: list[dict],
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> Reconstruction:
    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        raise ValueError("Reconstruction not found")
    if rec.status != "complete":
        raise ValueError("Reconstruction must be complete before video render")
    if rec.flythrough_status in {"pending", "running"}:
        raise ValueError(
            f"Flythrough render already running for reconstruction {reconstruction_id}"
        )

    normalized_keyframes = _validate_keyframes(keyframes)

    rec.flythrough_status = "pending"
    rec.flythrough_error = None
    db.commit()
    db.refresh(rec)

    enqueue(
        FLYTHROUGH_RENDER,
        reconstruction_id,
        payload={
            "keyframes": normalized_keyframes,
            "fps": fps,
            "width": width,
            "height": height,
        },
        priority=3,
    )
    return rec


def _run_flythrough_job(entry, db, cancel: threading.Event) -> None:
    """Job queue handler for flythrough render."""
    reconstruction_id = entry.target_id
    payload = entry.payload_json
    kw: dict = json.loads(payload) if payload else {}
    keyframes = kw.get("keyframes", [])
    fps = kw.get("fps", 30)
    width = kw.get("width", 1920)
    height = kw.get("height", 1080)

    rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
    if rec is None:
        return
    rec.flythrough_status = "running"
    rec.flythrough_error = None
    db.commit()

    try:
        if not rec.splat_path or not Path(rec.splat_path).exists():
            raise RuntimeError("Splat file not found on disk")
        output_path = _reconstruction_export_dir(rec.id) / "flythrough.mp4"
        rendered = _run_video_renderer(
            Path(rec.splat_path),
            output_path,
            keyframes,
            fps=fps,
            width=width,
            height=height,
        )
        rec.flythrough_path = str(rendered)
        rec.flythrough_status = "complete"
        rec.flythrough_error = None
        db.commit()
        mark_complete(entry.id)
    except Exception as exc:
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).update({
            "flythrough_status": "failed",
            "flythrough_error": str(exc)[:_ERROR_MSG_MAX_CHARS],
        })
        db.commit()
        raise


def _load_las_positions_and_colors(pointcloud_path: Path) -> tuple:
    """Return (Nx3 float64 XYZ, Nx3 uint8 RGB or None) from a LAS/LAZ file."""
    import laspy
    import numpy as np

    las = laspy.read(pointcloud_path)
    xyz = np.column_stack([las.x, las.y, las.z]).astype(np.float64)
    if not {"red", "green", "blue"} <= set(las.point_format.dimension_names):
        return xyz, None

    rgb = np.column_stack([las.red, las.green, las.blue]).astype(np.float64)
    # Point formats 2/3/5 always allocate the colour dimensions, so an all-zero
    # block means "never populated" rather than "black" — grey beats a black raster.
    if not rgb.any():
        return xyz, None
    # LAS colour is nominally 16-bit (our own export scales 8-bit up by 257),
    # but some producers leave 8-bit values in the field unscaled.
    if rgb.max() > 255:
        rgb /= 257.0
    return xyz, np.clip(rgb, 0, 255).astype(np.uint8)


def _load_las_positions(pointcloud_path: Path):
    """Positions only. Change detection voxelises this result and needs Nx3."""
    return _load_las_positions_and_colors(pointcloud_path)[0]


def _reproject_utm_points(points, source_geo: dict, target_geo: dict):
    import numpy as np
    from pyproj import Transformer

    source_epsg = _utm_epsg(str(source_geo.get("utm_zone", "")))
    target_epsg = _utm_epsg(str(target_geo.get("utm_zone", "")))
    if source_epsg is None or target_epsg is None or source_epsg == target_epsg:
        return points

    transformer = Transformer.from_crs(source_epsg, target_epsg, always_xy=True)
    x, y = transformer.transform(points[:, 0], points[:, 1])
    return np.column_stack([x, y, points[:, 2]]).astype(np.float64)


def _load_reconstruction_points_utm(rec: Reconstruction, target_geo: dict | None = None) -> tuple:
    geo = _load_geo_transform_for_reconstruction(rec)
    if rec.pointcloud_path and Path(rec.pointcloud_path).exists():
        points = _load_las_positions(Path(rec.pointcloud_path))
    elif rec.splat_path and Path(rec.splat_path).exists():
        points, _rgb = _load_ply_positions_and_colors(Path(rec.splat_path))
        points = _world_points_to_utm(points, geo)
    elif rec.colmap_dir:
        points, _rgb = _read_colmap_points3d(
            _pick_best_submodel(Path(rec.colmap_dir) / "sparse") / "points3D.txt"
        )
        points = _world_points_to_utm(points, geo)
    else:
        raise RuntimeError(f"Reconstruction {rec.id} has no point source")

    if target_geo is not None:
        points = _reproject_utm_points(points, geo, target_geo)
    return points, geo


def _voxelize_points(points, voxel_size_m: float) -> set[tuple[int, int, int]]:
    import numpy as np

    if len(points) == 0:
        return set()
    coords = np.floor(points / voxel_size_m).astype(np.int64)
    return {tuple(int(v) for v in row) for row in coords}


def _cells_from_voxels(
    voxels: set[tuple[int, int, int]],
    voxel_size_m: float,
    change_type: str,
) -> list[dict]:
    cells = []
    for vx, vy, vz in sorted(voxels):
        cells.append({
            "x": (vx + 0.5) * voxel_size_m,
            "y": (vy + 0.5) * voxel_size_m,
            "z": (vz + 0.5) * voxel_size_m,
            "size": voxel_size_m,
            "type": change_type,
        })
    return cells


def _compute_voxel_diff(
    rec_a: Reconstruction,
    rec_b: Reconstruction,
    output_path: Path,
    *,
    voxel_size_m: float = 0.5,
) -> dict:
    cfg = get_config()
    output_path = confine_path(output_path, Path(cfg.exports_dir))
    points_a, geo_a = _load_reconstruction_points_utm(rec_a)
    points_b, geo_b = _load_reconstruction_points_utm(rec_b, target_geo=geo_a)
    voxels_a = _voxelize_points(points_a, voxel_size_m)
    voxels_b = _voxelize_points(points_b, voxel_size_m)

    new_voxels = voxels_b - voxels_a
    removed_voxels = voxels_a - voxels_b
    diff = {
        "comparison": {
            "session_a_id": rec_a.session_id,
            "session_b_id": rec_b.session_id,
            "reconstruction_a_id": rec_a.id,
            "reconstruction_b_id": rec_b.id,
        },
        "voxel_size_m": voxel_size_m,
        "utm_zone": geo_a.get("utm_zone"),
        "summary": {
            "a_cells": len(voxels_a),
            "b_cells": len(voxels_b),
            "new_count": len(new_voxels),
            "removed_count": len(removed_voxels),
        },
        "new": _cells_from_voxels(new_voxels, voxel_size_m, "new"),
        "removed": _cells_from_voxels(removed_voxels, voxel_size_m, "removed"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diff, indent=2), encoding="utf-8")
    return diff


def diff_to_geojson(diff: dict) -> dict:
    transformer = None
    epsg = _utm_epsg(str(diff.get("utm_zone") or ""))
    if epsg is not None:
        from pyproj import Transformer

        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)

    features = []
    for change_type in ("new", "removed"):
        for cell in diff.get(change_type, []):
            x = float(cell["x"])
            y = float(cell["y"])
            z = float(cell["z"])
            if transformer is not None:
                lon, lat = transformer.transform(x, y)
                coordinates = [lon, lat, z]
            else:
                coordinates = [x, y, z]
            features.append({
                "type": "Feature",
                "properties": {
                    "type": change_type,
                    "size": cell["size"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": coordinates,
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "summary": diff.get("summary", {}),
            "comparison": diff.get("comparison", {}),
        },
    }


def start_session_comparison(
    session_a_id: int,
    session_b_id: int,
    reconstruction_a_id: int,
    reconstruction_b_id: int,
    db: DBSession,
    *,
    voxel_size_m: float = 0.5,
) -> SessionComparison:
    rec_a = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_a_id).first()
    rec_b = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_b_id).first()
    if rec_a is None or rec_b is None:
        raise ValueError("Reconstruction not found")
    if rec_a.session_id != session_a_id or rec_b.session_id != session_b_id:
        raise ValueError("Reconstruction does not belong to the requested session")
    if rec_a.status != "complete" or rec_b.status != "complete":
        raise ValueError("Both reconstructions must be complete before comparison")

    comparison = SessionComparison(
        session_a_id=session_a_id,
        session_b_id=session_b_id,
        reconstruction_a_id=reconstruction_a_id,
        reconstruction_b_id=reconstruction_b_id,
        status="pending",
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    enqueue(
        SESSION_COMPARISON,
        comparison.id,
        payload={"voxel_size_m": voxel_size_m},
        priority=1,
    )
    return comparison


def _run_comparison_job(entry, db, cancel: threading.Event) -> None:
    """Job queue handler for session comparison."""
    comparison_id = entry.target_id
    payload = entry.payload_json
    kw: dict = json.loads(payload) if payload else {}
    voxel_size_m = kw.get("voxel_size_m", 0.5)

    comparison = (
        db.query(SessionComparison).filter(SessionComparison.id == comparison_id).first()
    )
    if comparison is None:
        return
    comparison.status = "running"
    comparison.error_msg = None
    db.commit()

    try:
        rec_a = db.query(Reconstruction).filter(
            Reconstruction.id == comparison.reconstruction_a_id
        ).first()
        rec_b = db.query(Reconstruction).filter(
            Reconstruction.id == comparison.reconstruction_b_id
        ).first()
        if rec_a is None or rec_b is None:
            raise RuntimeError("Comparison reconstruction missing")

        cfg = get_config()
        output_path = Path(cfg.exports_dir) / "comparisons" / str(comparison_id) / "diff.json"
        _compute_voxel_diff(rec_a, rec_b, output_path, voxel_size_m=voxel_size_m)
        comparison.diff_path = str(output_path)
        comparison.status = "complete"
        comparison.completed_at = datetime.now(UTC)
        db.commit()
        mark_complete(entry.id)
    except Exception as exc:
        db.query(SessionComparison).filter(SessionComparison.id == comparison_id).update({
            "status": "failed",
            "error_msg": str(exc)[:_ERROR_MSG_MAX_CHARS],
            "completed_at": datetime.now(UTC),
        })
        db.commit()
        raise


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def start_reconstruction(
    session_id: int,
    preset: str,
    db: DBSession,
    *,
    target_area_geojson: str | None = None,
    source_session_ids: list[int] | None = None,
    parent_reconstruction_id: int | None = None,
    selected_image_ids: list[int] | None = None,
) -> Reconstruction:
    """Create Reconstruction record and enqueue a background job. Returns the record."""
    running = db.query(Reconstruction).filter(
        Reconstruction.session_id == session_id,
        Reconstruction.status.in_(["pending", "running_colmap", "running_gsplat"]),
    ).first()
    if running:
        raise ValueError(
            f"Reconstruction {running.id} already in progress for session {session_id}"
        )

    if source_session_ids is not None:
        # Multi-session merge: collect images from all sessions
        images = []
        for sid in source_session_ids:
            session_images = db.query(Image).filter(
                Image.session_id == sid,
                Image.usable == True,  # noqa: E712
            ).all()

            # Manual frame selection per session
            selected_rows = db.query(SessionFrameSelection).filter(
                SessionFrameSelection.session_id == sid
            ).all()
            if selected_rows:
                selected_ids_set = {row.image_id for row in selected_rows}
                session_images = [
                    img for img in session_images if img.id in selected_ids_set
                ]

            images.extend(session_images)

        if target_area_geojson:
            images = _filter_images_to_target_area(images, target_area_geojson)
    else:
        images = db.query(Image).filter(
            Image.session_id == session_id,
            Image.usable == True,  # noqa: E712
        ).all()

        if selected_image_ids is None:
            # Manual frame selection overrides the usable pool for ordinary runs.
            selected_rows = db.query(SessionFrameSelection).filter(
                SessionFrameSelection.session_id == session_id
            ).all()
            if selected_rows:
                selected_ids = {row.image_id for row in selected_rows}
                images = [img for img in images if img.id in selected_ids]
        else:
            # A lineage-aware rerun supplies an immutable selection.  Do not
            # read or alter the user's session-level selection preference.
            selected_ids = set(selected_image_ids)
            images = [img for img in images if img.id in selected_ids]
            if len(images) != len(selected_ids):
                raise ValueError("Dense rerun selection includes unavailable or unusable images")

        # Target area crop filters the pool
        if target_area_geojson:
            images = _filter_images_to_target_area(images, target_area_geojson)

    if not images:
        raise ValueError("No usable images in session")

    cfg = get_config()
    rec = Reconstruction(
        session_id=session_id,
        preset=preset,
        status="pending",
        frames_used=len(images),
        source_session_ids=json.dumps(source_session_ids) if source_session_ids else None,
        parent_reconstruction_id=parent_reconstruction_id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    colmap_dir = Path(cfg.data_dir) / "colmap" / str(rec.id)
    rec.colmap_dir = str(colmap_dir)
    db.commit()
    db.refresh(rec)

    for img in images:
        db.add(ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id))
    db.commit()

    image_ids = [img.id for img in images]

    # Enqueue persistent job instead of daemon thread
    enqueue(
        RECONSTRUCTION,
        rec.id,
        payload={"preset": preset, "colmap_dir": str(colmap_dir), "image_ids": image_ids},
        priority=10,
        max_attempts=2,
    )

    db.refresh(rec)
    return rec


def cancel_reconstruction(reconstruction_id: int) -> None:
    """Signal the reconstruction to stop and terminate its running COLMAP subprocess.

    Cancelling the job queue entry sets the cancel Event the pipeline polls; that
    stops Gaussian Splatting between iterations. COLMAP shells out to a blocking
    subprocess, so it is killed directly instead of waiting for the current step
    to finish (which can take 30+ minutes). The event is set *before* the kill so
    the killed COLMAP step surfaces as cancellation rather than a failure.
    """
    # Cancel the job queue entry first so the pipeline's cancel Event is set
    # before the COLMAP subprocess is terminated.
    from backend.services.job_queue import cancel_job as _cancel_job
    db = SessionLocal()
    try:
        entry = (
            db.query(JobQueueEntry)
            .filter(
                JobQueueEntry.job_type == "reconstruction",
                JobQueueEntry.target_id == reconstruction_id,
                JobQueueEntry.status.in_(["pending", "running"]),
            )
            .first()
        )
        if entry is not None:
            _cancel_job(entry.id)
    finally:
        db.close()
    _kill_running_subprocess(reconstruction_id)


def _update_rec(db: DBSession, rec_id: int, **kwargs) -> None:
    if "completed_at" in kwargs and "duration_s" not in kwargs:
        started_at = (
            db.query(Reconstruction.started_at)
            .filter(Reconstruction.id == rec_id)
            .scalar()
        )
        kwargs["duration_s"] = _duration_seconds(started_at, kwargs["completed_at"])
    db.query(Reconstruction).filter(Reconstruction.id == rec_id).update(kwargs)
    db.commit()
    notify_reconstruction_status_changed(rec_id)


def _duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if started_at is None or completed_at is None:
        return None
    if started_at.tzinfo is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    elif started_at.tzinfo is None and completed_at.tzinfo is not None:
        started_at = started_at.replace(tzinfo=UTC)
    return max(0.0, (completed_at - started_at).total_seconds())


def _run_pipeline(entry, db, cancel: threading.Event) -> None:
    """Job queue handler for reconstruction pipeline."""
    reconstruction_id = entry.target_id
    payload = entry.payload_json
    kw: dict = json.loads(payload) if payload else {}
    preset = kw.get("preset", "quick")
    colmap_dir = Path(kw.get("colmap_dir", ""))
    image_ids = kw.get("image_ids", [])
    remote_cfg = get_remote_worker_config()
    if remote_cfg["enabled"]:
        _run_remote_pipeline(entry, db, cancel, kw, remote_cfg)
        mark_complete(entry.id)
        return
    try:
        images = db.query(Image).filter(Image.id.in_(image_ids)).all()
        recon_cfg = get_reconstruction_config()
        preset_cfg = recon_cfg["presets"][preset]

        _update_rec(
            db, reconstruction_id,
            status="running_colmap", step="writing workspace", progress_pct=2.0,
        )
        _log_rec(reconstruction_id, "COLMAP: starting")
        calibration = calibration_profile_for_images(
            images,
            recon_cfg.get("camera_profiles", []),
            get_config().image_width_px,
            get_config().image_height_px,
            get_config().fov_horizontal_deg,
            get_config().fov_vertical_deg,
            recon_cfg.get("camera_model", "PINHOLE"),
        )
        profile = calibration.get("profile")
        if profile:
            _log_rec(reconstruction_id, f"Camera calibration profile: {profile.get('name')}")
        suggested_model = calibration["suggested_colmap_camera_model"]
        configured_model = calibration["configured_colmap_camera_model"]
        if suggested_model != configured_model:
            _log_rec(
                reconstruction_id,
                "COLMAP camera model suggestion: "
                f"{suggested_model} (configured {configured_model})",
            )
        for warning in calibration["warnings"]:
            _log_rec(reconstruction_id, f"Camera calibration warning: {warning}")
        _write_colmap_workspace(colmap_dir, images)

        if cancel.is_set():
            _update_rec(
                db, reconstruction_id,
                status="cancelled",
                step="cancelled",
                error_msg="Cancelled by user",
                completed_at=datetime.now(UTC),
            )
            return

        def progress_cb(step: str, pct: float) -> None:
            _update_rec(db, reconstruction_id, step=step, progress_pct=pct)

        # Determine GPS presence + image count for spatial_matcher selection
        gps_images = [
            img for img in images
            if img.latitude is not None and img.longitude is not None
        ]
        frames_registered = _run_colmap(
            colmap_dir,
            progress_cb,
            cancel,
            reconstruction_id=reconstruction_id,
            images_have_gps=len(gps_images) == len(images) and len(images) > 0,
            image_count=len(images),
        )
        _log_rec(reconstruction_id, "COLMAP: complete")
        _store_reprojection_errors(db, reconstruction_id, colmap_dir)

        if cancel.is_set():
            _update_rec(
                db, reconstruction_id,
                status="cancelled",
                step="cancelled",
                error_msg="Cancelled by user",
                completed_at=datetime.now(UTC),
            )
            return

        geo = _compute_geo_transform(reconstruction_id, colmap_dir, images)
        _update_rec(
            db, reconstruction_id,
            geo_transform=json.dumps(geo) if geo else None,
            frames_registered=frames_registered,
        )

        _update_rec(
            db, reconstruction_id, status="running_gsplat", step="training", progress_pct=40.0,
        )
        _log_rec(reconstruction_id, "Gaussian Splatting: starting")

        cfg = get_config()
        splat_path = Path(cfg.exports_dir) / str(reconstruction_id) / "splat.ply"
        splat_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = _run_gsplat(colmap_dir, splat_path, preset_cfg, progress_cb, cancel)
            training_metrics = result.get("training_metrics")
            _log_rec(reconstruction_id, "Gaussian Splatting: complete")
            _log_rec(reconstruction_id, "LOD generation: starting")
            preview, medium = _generate_lod(splat_path)
            _log_rec(reconstruction_id, "LOD generation: complete")

            _log_rec(reconstruction_id, "Thumbnail generation: starting")
            thumb_candidate = Path(cfg.processed_dir) / "thumbs" / f"splat_{reconstruction_id}.jpg"
            generated_thumb = _generate_thumbnail(splat_path, thumb_candidate)
            _log_rec(reconstruction_id, "Thumbnail generation: complete")

            completed_at = datetime.now(UTC)
            _update_rec(
                db, reconstruction_id,
                status="complete",
                step="done",
                progress_pct=100.0,
                splat_path=str(splat_path),
                splat_preview_path=str(preview),
                splat_medium_path=str(medium),
                thumb_path=str(generated_thumb) if generated_thumb else None,
                gaussian_count=result.get("gaussian_count"),
                psnr=result.get("psnr"),
                ssim=result.get("ssim"),
                training_metrics=json.dumps(training_metrics) if training_metrics else None,
                completed_at=completed_at,
            )
            _log_rec(reconstruction_id, "Pipeline complete")
        except ReconstructionCancelled:
            # Must precede the RuntimeError branch (it is a RuntimeError subclass):
            # a mid-training cancel is a failure, not a colmap_only completion.
            checkpoint_saved = splat_path.exists()
            if checkpoint_saved:
                _log_rec(
                    reconstruction_id,
                    f"Gaussian Splatting: cancellation checkpoint saved to {splat_path}",
                )
            _update_rec(
                db, reconstruction_id,
                status="cancelled",
                step="cancelled_checkpoint" if checkpoint_saved else "cancelled",
                splat_path=str(splat_path) if checkpoint_saved else None,
                error_msg=(
                    f"Cancelled by user; checkpoint saved to {splat_path}"
                    if checkpoint_saved else "Cancelled by user"
                ),
                completed_at=datetime.now(UTC),
            )
        except RuntimeError as exc:
            if "CUDA out of memory" in str(exc):
                _update_rec(
                    db, reconstruction_id,
                    status="failed",
                    error_msg=(
                        "GPU ran out of memory — switch to 'quick' preset or reduce frame count"
                    ),
                    completed_at=datetime.now(UTC),
                )
            elif "COLMAP sparse cloud only" in str(exc):
                # The trainer's documented graceful-degradation contract: missing
                # torch/gsplat is the only RuntimeError that means "COLMAP-only
                # success". Key on the message family, not the exception type —
                # every other trainer RuntimeError is a real failure.
                _log_rec(reconstruction_id, f"Gaussian Splatting skipped: {exc}")
                _update_rec(
                    db, reconstruction_id,
                    status="complete",
                    step="colmap_only",
                    progress_pct=100.0,
                    completed_at=datetime.now(UTC),
                )
                _log_rec(reconstruction_id, "Pipeline complete (COLMAP only)")
            else:
                # Unsupported camera model, empty sparse model, missing frame, ...
                _log_rec(reconstruction_id, f"Gaussian Splatting failed: {exc}")
                _update_rec(
                    db, reconstruction_id,
                    status="failed",
                    error_msg=str(exc)[:_ERROR_MSG_MAX_CHARS],
                    completed_at=datetime.now(UTC),
                )

    except Exception as exc:
        _update_rec(
            db, reconstruction_id,
            status="failed",
            error_msg=str(exc)[:_ERROR_MSG_MAX_CHARS],
            completed_at=datetime.now(UTC),
        )
        raise
    else:
        mark_complete(entry.id)


def _cancel_remote_best_effort(config: dict, remote_job_id, reconstruction_id: int) -> None:
    """Best-effort remote cancel so a terminal local transition never orphans a remote job."""
    if not (isinstance(remote_job_id, str) and remote_job_id):
        return
    try:
        cancel_remote_reconstruction(config, remote_job_id)
    except RemoteWorkerError:
        logger.warning("Remote cancel for job %s failed", remote_job_id)
        _log_rec(reconstruction_id, "Remote worker cancellation request failed")


def _run_remote_pipeline(
    entry, db: DBSession, cancel: threading.Event, payload: dict, config: dict
) -> None:
    """Dispatch once and poll a configured shared-storage worker through the existing queue."""
    reconstruction_id = entry.target_id
    remote_job_id = payload.get("remote_job_id")
    consecutive_failures = 0
    last_success = time.monotonic()
    try:
        if not isinstance(remote_job_id, str) or not remote_job_id:
            remote_job_id = dispatch_reconstruction(config, payload, reconstruction_id, entry.id)
            update_payload(entry.id, remote_job_id=remote_job_id)
            _log_rec(reconstruction_id, f"Remote worker accepted job {remote_job_id}")

        while not cancel.is_set():
            try:
                status = get_reconstruction_status(config, remote_job_id)
            except RemoteWorkerError as exc:
                consecutive_failures += 1
                elapsed = time.monotonic() - last_success
                logger.warning(
                    "Remote poll for reconstruction %s failed (attempt %d/%d): %s",
                    reconstruction_id,
                    consecutive_failures,
                    _REMOTE_POLL_MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
                _log_rec(
                    reconstruction_id,
                    f"Remote poll failed (attempt {consecutive_failures}): {exc}",
                )
                if (
                    consecutive_failures >= _REMOTE_POLL_MAX_CONSECUTIVE_FAILURES
                    and elapsed >= _REMOTE_POLL_FAILURE_WINDOW_S
                ):
                    raise RemoteWorkerError(
                        f"Remote worker unreachable for {int(elapsed)}s after "
                        f"{consecutive_failures} consecutive poll failures: {exc}"
                    ) from exc
                cancel.wait(config["poll_interval_seconds"])
                continue
            consecutive_failures = 0
            last_success = time.monotonic()
            state = status.get("status")
            if state in {"queued", "running"}:
                _update_rec(
                    db,
                    reconstruction_id,
                    status="running_remote",
                    step=str(status.get("step", "remote worker"))[:200],
                    progress_pct=float(status.get("progress_pct", 0.0)),
                )
                cancel.wait(config["poll_interval_seconds"])
                continue
            if state == "complete":
                result = status.get("result", {})
                result = result if isinstance(result, dict) else {}
                # Worker and API share storage, so the sparse model lands locally
                # at colmap_dir. Run the same in-process solve; leave the transform
                # NULL (never a placeholder) if no local sparse model is present.
                geo = None
                colmap_dir = payload.get("colmap_dir")
                if colmap_dir:
                    images = db.query(Image).filter(
                        Image.id.in_(payload.get("image_ids", []))
                    ).all()
                    geo = _compute_geo_transform(reconstruction_id, Path(colmap_dir), images)
                _update_rec(
                    db,
                    reconstruction_id,
                    status="complete",
                    step="done",
                    progress_pct=100.0,
                    frames_registered=result.get("frames_registered"),
                    gaussian_count=result.get("gaussian_count"),
                    psnr=result.get("psnr"),
                    ssim=result.get("ssim"),
                    geo_transform=json.dumps(geo) if geo else None,
                    completed_at=datetime.now(UTC),
                )
                _log_rec(reconstruction_id, "Remote worker: complete")
                return
            if state == "cancelled":
                message = str(status.get("error", "Remote worker cancelled"))[
                    :_ERROR_MSG_MAX_CHARS
                ]
                _update_rec(
                    db,
                    reconstruction_id,
                    status="cancelled",
                    step="cancelled",
                    error_msg=message,
                    completed_at=datetime.now(UTC),
                )
                entry.status = "cancelled"
                entry.completed_at = datetime.now(UTC)
                db.commit()
                return
            if state == "failed":
                message = str(status.get("error", f"Remote worker {state}"))[:_ERROR_MSG_MAX_CHARS]
                _update_rec(
                    db,
                    reconstruction_id,
                    status=state,
                    step=state,
                    error_msg=message,
                    completed_at=datetime.now(UTC),
                )
                raise JobNonRetryableError(message)
            raise RemoteWorkerError("Remote worker returned an unknown job status")
    except RemoteWorkerError as exc:
        _update_rec(
            db,
            reconstruction_id,
            status="failed",
            step="remote worker error",
            error_msg=str(exc)[:_ERROR_MSG_MAX_CHARS],
            completed_at=datetime.now(UTC),
        )
        _cancel_remote_best_effort(config, remote_job_id, reconstruction_id)
        raise JobNonRetryableError(str(exc)) from exc
    if cancel.is_set():
        _cancel_remote_best_effort(config, remote_job_id, reconstruction_id)
        _update_rec(
            db,
            reconstruction_id,
            status="cancelled",
            step="cancelled",
            error_msg="Cancelled by user",
            completed_at=datetime.now(UTC),
        )


# Register job queue handlers at import time so they're available when
# the worker drains the queue.
register_handler(RECONSTRUCTION, _run_pipeline)
register_handler(MESH_EXPORT, _run_mesh_export_job)
register_handler(FLYTHROUGH_RENDER, _run_flythrough_job)
register_handler(SESSION_COMPARISON, _run_comparison_job)


# ---------------------------------------------------------------------------
# Backward-compatible wrappers — called directly by unit tests.
# These construct a mock JobQueueEntry and delegate to the new handler
# signature so existing tests don't need to change.
# ---------------------------------------------------------------------------

class _FakeEntry:
    """Minimal duck-type so tests can call handlers directly."""
    __slots__ = ("id", "job_type", "target_id", "payload_json", "status",
                 "priority", "attempt", "max_attempts", "created_at",
                 "started_at", "completed_at", "error_msg")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _run_pipeline_legacy(
    reconstruction_id: int,
    preset: str,
    colmap_dir: Path,
    image_ids: list[int],
    cancel: threading.Event,
) -> None:
    db = SessionLocal()
    try:
        entry = _FakeEntry(
            id=-1, job_type=RECONSTRUCTION, target_id=reconstruction_id,
            payload_json=json.dumps({"preset": preset, "colmap_dir": str(colmap_dir),
                                     "image_ids": image_ids}),
            max_attempts=1, attempt=0,
        )
        _run_pipeline(entry, db, cancel)
    except Exception:
        pass  # Target entity already updated; legacy caller just needs the side effect
    finally:
        db.close()


def _run_mesh_export_job_legacy(reconstruction_id: int) -> None:
    db = SessionLocal()
    try:
        entry = _FakeEntry(id=-1, job_type=MESH_EXPORT, target_id=reconstruction_id,
                          max_attempts=1, attempt=0)
        _run_mesh_export_job(entry, db, threading.Event())
    except Exception:
        pass  # Target entity already updated; legacy caller just needs the side effect
    finally:
        db.close()


def _run_flythrough_job_legacy(
    reconstruction_id: int,
    keyframes: list[dict],
    fps: int,
    width: int,
    height: int,
) -> None:
    db = SessionLocal()
    try:
        entry = _FakeEntry(
            id=-1, job_type=FLYTHROUGH_RENDER, target_id=reconstruction_id,
            payload_json=json.dumps({"keyframes": keyframes, "fps": fps,
                                     "width": width, "height": height}),
            max_attempts=1, attempt=0,
        )
        _run_flythrough_job(entry, db, threading.Event())
    except Exception:
        pass  # Target entity already updated; legacy caller just needs the side effect
    finally:
        db.close()
