from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, shape
from sqlalchemy.orm import Session as DBSession

from backend.core.config import get_config, get_reconstruction_config
from backend.db.database import SessionLocal
from backend.db.models import Image, Reconstruction, ReconstructionFrame, SessionFrameSelection

# Maps reconstruction_id → cancel Event
_cancel_events: dict[int, threading.Event] = {}

_rec_logs: dict[int, list[str]] = {}
_rec_logs_lock = threading.Lock()


def _log_rec(rec_id: int, msg: str) -> None:
    with _rec_logs_lock:
        buf = _rec_logs.setdefault(rec_id, [])
        buf.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}")
        if len(buf) > 500:
            _rec_logs[rec_id] = buf[-500:]


def get_rec_log(rec_id: int) -> list[str]:
    with _rec_logs_lock:
        return list(_rec_logs.get(rec_id, []))


# ---------------------------------------------------------------------------
# Workspace writer
# ---------------------------------------------------------------------------

def _write_colmap_workspace(colmap_dir: Path, images: list) -> None:
    """Create COLMAP workspace directory structure and seed cameras.txt."""
    images_dir = colmap_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    (colmap_dir / "sparse").mkdir(parents=True, exist_ok=True)

    cfg = get_config()
    f_px = (cfg.image_width_px / 2) / math.tan(math.radians(cfg.fov_horizontal_deg / 2))
    cx = cfg.image_width_px / 2
    cy = cfg.image_height_px / 2
    cameras_txt = colmap_dir / "cameras.txt"
    cameras_txt.write_text(
        "# Camera list with one line of data per camera:\n"
        "#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n"
        f"1 PINHOLE {cfg.image_width_px} {cfg.image_height_px} "
        f"{f_px:.4f} {f_px:.4f} {cx:.4f} {cy:.4f}\n"
    )

    for img in images:
        src = Path(img.filepath)
        dest = images_dir / img.filename
        if dest.exists():
            continue
        try:
            os.symlink(src.resolve(), dest)
        except (OSError, NotImplementedError):
            shutil.copy2(src, dest)


# ---------------------------------------------------------------------------
# COLMAP subprocess runner
# ---------------------------------------------------------------------------

def _run_colmap(colmap_dir: Path, progress_cb, cancel: threading.Event) -> None:
    """Run COLMAP feature_extractor → exhaustive_matcher → mapper pipeline."""
    db_path = str(colmap_dir / "database.db")
    image_path = str(colmap_dir / "images")
    output_path = str(colmap_dir / "sparse")
    cfg = get_reconstruction_config()

    steps = [
        (
            ["colmap", "feature_extractor",
             "--database_path", db_path,
             "--image_path", image_path,
             f"--SiftExtraction.max_num_features={cfg['sift_max_features']}",
             "--ImageReader.camera_model", "PINHOLE",
             "--ImageReader.single_camera", "1"],
            "feature extraction",
            10.0,
        ),
        (
            ["colmap", "exhaustive_matcher",
             "--database_path", db_path],
            "feature matching",
            40.0,
        ),
        (
            ["colmap", "mapper",
             "--database_path", db_path,
             "--image_path", image_path,
             "--output_path", output_path,
             f"--Mapper.num_threads={cfg['colmap_threads']}"],
            "bundle adjustment",
            80.0,
        ),
        (
            ["colmap", "model_converter",
             "--input_path", str(colmap_dir / "sparse" / "0"),
             "--output_path", str(colmap_dir / "sparse" / "0"),
             "--output_type", "TXT"],
            "model conversion",
            90.0,
        ),
    ]

    for cmd, step_name, pct in steps:
        if cancel.is_set():
            return
        progress_cb(step_name, pct)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"COLMAP {step_name} failed: {result.stderr[:500]}"
            )

    images_txt = colmap_dir / "sparse" / "0" / "images.txt"
    if not images_txt.exists() or _count_registered_images(images_txt) == 0:
        raise RuntimeError(
            "Not enough feature matches — add more overlapping frames or reduce altitude"
        )

    progress_cb("colmap complete", 95.0)


def _count_registered_images(images_txt: Path) -> int:
    count = 0
    for line in images_txt.read_text().splitlines():
        if line and not line.startswith("#") and not line.startswith(" "):
            count += 1
    return count // 2  # each image is 2 lines in COLMAP TXT format


def _store_reprojection_errors(db: DBSession, reconstruction_id: int, colmap_dir: Path) -> None:
    """Read COLMAP TXT output and write per-frame mean reprojection error to DB."""
    points3d_txt = colmap_dir / "sparse" / "0" / "points3D.txt"
    images_txt = colmap_dir / "sparse" / "0" / "images.txt"
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
    return [
        {"iter": int(m.group(1)), "psnr": float(m.group(2)), "ssim": float(m.group(3))}
        for m in _CHECKPOINT_RE.finditer(output)
    ]


def _compute_coverage_gaps(
    splat_path: Path, output_path: Path, voxel_size_m: float = 0.5
) -> list[dict]:
    """Voxelize Gaussian positions from .ply and classify sparse cells."""
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
        return []

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
        if ratio < 0.10:
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
    return cells


def _extract_geo_transform(colmap_dir: Path) -> dict:
    """Extract similarity transform from COLMAP model. Returns placeholder if unavailable."""
    geo_ref = colmap_dir / "geo_transform.json"
    if geo_ref.exists():
        return json.loads(geo_ref.read_text())
    return {
        "scale": 1.0,
        "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation": [0.0, 0.0, 0.0],
        "utm_zone": "unknown",
        "utm_origin": [0.0, 0.0],
    }


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
    colmap_dir: Path, output_path: Path, iterations: int, progress_cb, cancel: threading.Event
) -> dict:
    """Train a Gaussian splat. Returns {gaussian_count, psnr, ssim, training_metrics}."""
    import contextlib
    import io

    try:
        from gsplat import train  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "gsplat is not installed. Run: pip install '.[reconstruction]'"
        ) from exc

    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        result = train(
            colmap_dir=str(colmap_dir),
            output_path=str(output_path),
            iterations=iterations,
            progress_cb=progress_cb,
            cancel=cancel,
        )

    metrics = _parse_checkpoint_metrics(stdout_buf.getvalue())
    result["training_metrics"] = metrics if metrics else None
    return result


def _generate_lod(splat_path: Path) -> tuple[Path, Path]:
    """Return (preview_path, medium_path) — 10% and 50% pruned variants."""
    preview = splat_path.with_name(splat_path.stem + "_preview.ply")
    medium = splat_path.with_name(splat_path.stem + "_medium.ply")
    try:
        from gsplat import prune_by_opacity  # type: ignore[import]
        prune_by_opacity(str(splat_path), str(preview), keep_ratio=0.10)
        prune_by_opacity(str(splat_path), str(medium), keep_ratio=0.50)
    except ImportError:
        pass
    return preview, medium


def _generate_thumbnail(splat_path: Path, out_path: Path) -> Path | None:
    """Render a 512×512 nadir-view JPEG thumbnail using gsplat's offline renderer.
    Returns out_path on success, None if gsplat is unavailable."""
    try:
        import gsplat  # type: ignore[import]
        render_nadir = gsplat.render_nadir
    except (ImportError, AttributeError):
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    render_nadir(str(splat_path), str(out_path), width=512, height=512)
    return out_path


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def start_reconstruction(
    session_id: int,
    preset: str,
    db: DBSession,
    *,
    target_area_geojson: str | None = None,
) -> Reconstruction:
    """Create Reconstruction record and launch background thread. Returns the record."""
    running = db.query(Reconstruction).filter(
        Reconstruction.session_id == session_id,
        Reconstruction.status.in_(["pending", "running_colmap", "running_gsplat"]),
    ).first()
    if running:
        raise ValueError(
            f"Reconstruction {running.id} already in progress for session {session_id}"
        )

    images = db.query(Image).filter(
        Image.session_id == session_id,
        Image.usable == True,  # noqa: E712
    ).all()

    # Manual frame selection overrides the usable pool
    selected_rows = db.query(SessionFrameSelection).filter(
        SessionFrameSelection.session_id == session_id
    ).all()
    if selected_rows:
        selected_ids = {row.image_id for row in selected_rows}
        images = [img for img in images if img.id in selected_ids]

    # Target area crop filters the pool
    if target_area_geojson:
        images = _filter_images_to_target_area(images, target_area_geojson)

    if not images:
        raise ValueError("No usable images in session")

    cfg = get_config()
    colmap_dir = Path(cfg.data_dir) / "colmap" / str(session_id)

    rec = Reconstruction(
        session_id=session_id,
        preset=preset,
        status="pending",
        frames_used=len(images),
        colmap_dir=str(colmap_dir),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    for img in images:
        db.add(ReconstructionFrame(reconstruction_id=rec.id, image_id=img.id))
    db.commit()

    cancel_event = threading.Event()
    _cancel_events[rec.id] = cancel_event

    image_ids = [img.id for img in images]
    threading.Thread(
        target=_run_pipeline,
        args=(rec.id, preset, colmap_dir, image_ids, cancel_event),
        daemon=True,
    ).start()

    db.refresh(rec)
    return rec


def cancel_reconstruction(reconstruction_id: int) -> None:
    """Signal the background thread to stop between pipeline steps."""
    event = _cancel_events.get(reconstruction_id)
    if event:
        event.set()


def _update_rec(db: DBSession, rec_id: int, **kwargs) -> None:
    db.query(Reconstruction).filter(Reconstruction.id == rec_id).update(kwargs)
    db.commit()


def _run_pipeline(
    reconstruction_id: int,
    preset: str,
    colmap_dir: Path,
    image_ids: list[int],
    cancel: threading.Event,
) -> None:
    db = SessionLocal()
    try:
        images = db.query(Image).filter(Image.id.in_(image_ids)).all()
        recon_cfg = get_reconstruction_config()
        preset_cfg = recon_cfg["presets"][preset]

        _update_rec(
            db, reconstruction_id,
            status="running_colmap", step="writing workspace", progress_pct=2.0,
        )
        _log_rec(reconstruction_id, "COLMAP: starting")
        _write_colmap_workspace(colmap_dir, images)

        if cancel.is_set():
            _update_rec(
                db, reconstruction_id,
                status="failed",
                error_msg="Cancelled by user",
                completed_at=datetime.now(timezone.utc),
            )
            return

        def progress_cb(step: str, pct: float) -> None:
            _update_rec(db, reconstruction_id, step=step, progress_pct=pct)

        _run_colmap(colmap_dir, progress_cb, cancel)
        _log_rec(reconstruction_id, "COLMAP: complete")
        _store_reprojection_errors(db, reconstruction_id, colmap_dir)

        if cancel.is_set():
            _update_rec(
                db, reconstruction_id,
                status="failed",
                error_msg="Cancelled by user",
                completed_at=datetime.now(timezone.utc),
            )
            return

        geo = _extract_geo_transform(colmap_dir)
        _update_rec(db, reconstruction_id, geo_transform=json.dumps(geo))

        _update_rec(
            db, reconstruction_id, status="running_gsplat", step="training", progress_pct=95.0,
        )
        _log_rec(reconstruction_id, "Gaussian Splatting: starting")

        cfg = get_config()
        splat_path = Path(cfg.exports_dir) / str(reconstruction_id) / "splat.ply"
        splat_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = _run_gsplat(
                colmap_dir, splat_path, preset_cfg["iterations"], progress_cb, cancel
            )
            training_metrics = result.get("training_metrics")
            _log_rec(reconstruction_id, "Gaussian Splatting: complete")
            _log_rec(reconstruction_id, "LOD generation: starting")
            preview, medium = _generate_lod(splat_path)
            _log_rec(reconstruction_id, "LOD generation: complete")

            _log_rec(reconstruction_id, "Thumbnail generation: starting")
            thumb_candidate = Path(cfg.processed_dir) / "thumbs" / f"splat_{reconstruction_id}.jpg"
            generated_thumb = _generate_thumbnail(splat_path, thumb_candidate)
            _log_rec(reconstruction_id, "Thumbnail generation: complete")

            completed_at = datetime.now(timezone.utc)
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
        except RuntimeError as exc:
            if "CUDA out of memory" in str(exc):
                _update_rec(
                    db, reconstruction_id,
                    status="failed",
                    error_msg=(
                        "GPU ran out of memory — switch to 'quick' preset or reduce frame count"
                    ),
                    completed_at=datetime.now(timezone.utc),
                )
            else:
                raise

    except Exception as exc:
        _update_rec(
            db, reconstruction_id,
            status="failed", error_msg=str(exc)[:500], completed_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()
        _cancel_events.pop(reconstruction_id, None)
