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
from backend.db.models import (
    Image,
    Reconstruction,
    ReconstructionFrame,
    SessionComparison,
    SessionFrameSelection,
)

# Maps reconstruction_id → cancel Event
_cancel_events: dict[int, threading.Event] = {}

_rec_logs: dict[int, list[str]] = {}
_rec_logs_lock = threading.Lock()
_mesh_jobs: set[int] = set()
_mesh_jobs_lock = threading.Lock()
_flythrough_jobs: set[int] = set()
_flythrough_jobs_lock = threading.Lock()
_comparison_jobs: set[int] = set()
_comparison_jobs_lock = threading.Lock()


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


def _nearest_gaussian_colors(points_xyz, gaussian_xyz, gaussian_rgb, fallback_rgb):
    """Color each COLMAP point from the nearest Gaussian, falling back to COLMAP RGB."""
    import numpy as np

    if gaussian_rgb is None or len(gaussian_xyz) == 0:
        return fallback_rgb

    colors = np.empty((len(points_xyz), 3), dtype=np.uint8)
    chunk_size = 512
    for start in range(0, len(points_xyz), chunk_size):
        stop = min(start + chunk_size, len(points_xyz))
        chunk = points_xyz[start:stop]
        distances = ((chunk[:, None, :] - gaussian_xyz[None, :, :]) ** 2).sum(axis=2)
        nearest = np.argmin(distances, axis=1)
        colors[start:stop] = np.clip(gaussian_rgb[nearest], 0, 255).astype(np.uint8)
    return colors


def _utm_epsg(utm_zone: str) -> int | None:
    match = re.match(r"^(\d{1,2})([NS])$", utm_zone, re.IGNORECASE)
    if not match:
        return None
    zone = int(match.group(1))
    if zone < 1 or zone > 60:
        return None
    return (32600 if match.group(2).upper() == "N" else 32700) + zone


def _world_points_to_utm(points_xyz, geo: dict):
    import numpy as np

    if _utm_epsg(str(geo.get("utm_zone", ""))) is None:
        return points_xyz

    rotation = np.array(geo["rotation"], dtype=np.float64)
    translation = np.array(geo["translation"], dtype=np.float64)
    origin = np.array([geo["utm_origin"][0], geo["utm_origin"][1], 0.0], dtype=np.float64)
    transformed = float(geo["scale"]) * (points_xyz @ rotation.T) + translation + origin
    return transformed


def _export_point_cloud(colmap_dir: Path, splat_path: Path, output_path: Path) -> Path:
    """Export COLMAP sparse points as a colored LAS 1.4 point cloud."""
    import laspy
    import numpy as np
    from pyproj import CRS

    cfg = get_config()
    output_path = _safe_export_path(output_path, Path(cfg.exports_dir))

    points_xyz, colmap_rgb = _read_colmap_points3d(colmap_dir / "sparse" / "0" / "points3D.txt")
    gaussian_xyz, gaussian_rgb = _load_ply_positions_and_colors(splat_path)
    colors = _nearest_gaussian_colors(points_xyz, gaussian_xyz, gaussian_rgb, colmap_rgb)

    geo = _extract_geo_transform(colmap_dir)
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    las.write(output_path)
    return output_path


# ---------------------------------------------------------------------------
# Phase 7 exports: mesh, flythrough video, multi-session comparison
# ---------------------------------------------------------------------------

def _reconstruction_export_dir(reconstruction_id: int) -> Path:
    cfg = get_config()
    return Path(cfg.exports_dir) / str(reconstruction_id)


def _safe_export_path(path: Path, exports_dir: Path) -> Path:
    exports_root = os.path.normpath(os.path.realpath(exports_dir))
    candidate = os.path.normpath(os.path.realpath(path))
    exports_root_cmp = os.path.normcase(exports_root)
    candidate_cmp = os.path.normcase(candidate)
    exports_prefix = (
        exports_root_cmp
        if exports_root_cmp.endswith(os.sep)
        else f"{exports_root_cmp}{os.sep}"
    )
    if candidate_cmp != exports_root_cmp and not candidate_cmp.startswith(exports_prefix):
        raise ValueError(f"Export path {path} is outside exports directory")
    return Path(candidate)


def _load_geo_transform_for_reconstruction(rec: Reconstruction) -> dict:
    if rec.geo_transform:
        return json.loads(rec.geo_transform)
    if rec.colmap_dir:
        return _extract_geo_transform(Path(rec.colmap_dir))
    return _extract_geo_transform(Path(""))


def _mesh_georef_metadata(rec: Reconstruction, geo: dict) -> dict:
    return {
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
                "SuGaR is not installed. Install optional reconstruction dependencies."
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

    with _mesh_jobs_lock:
        if reconstruction_id in _mesh_jobs:
            raise ValueError(f"Mesh export already running for reconstruction {reconstruction_id}")
        _mesh_jobs.add(reconstruction_id)

    rec.mesh_status = "pending"
    rec.mesh_error = None
    db.commit()
    db.refresh(rec)

    threading.Thread(target=_run_mesh_export_job, args=(reconstruction_id,), daemon=True).start()
    return rec


def _run_mesh_export_job(reconstruction_id: int) -> None:
    db = SessionLocal()
    try:
        rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
        if rec is None:
            return
        rec.mesh_status = "running"
        rec.mesh_error = None
        db.commit()

        outputs = _export_mesh_assets(rec)
        rec.mesh_glb_path = str(outputs["glb"]) if outputs["glb"] else None
        rec.mesh_obj_path = str(outputs["obj"]) if outputs["obj"] else None
        rec.mesh_mtl_path = str(outputs["mtl"]) if outputs["mtl"] else None
        rec.mesh_status = "complete"
        rec.mesh_error = None
        db.commit()
    except Exception as exc:
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).update({
            "mesh_status": "failed",
            "mesh_error": str(exc)[:500],
        })
        db.commit()
    finally:
        db.close()
        with _mesh_jobs_lock:
            _mesh_jobs.discard(reconstruction_id)


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
    try:
        import gsplat  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "gsplat video rendering is not installed. Use browser recording or install "
            "optional reconstruction dependencies."
        ) from exc

    render_video = getattr(gsplat, "render_video", None)
    if render_video is None:
        raise RuntimeError("Installed gsplat package does not expose render_video")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_video(
        splat_path=str(splat_path),
        output_path=str(output_path),
        keyframes=keyframes,
        fps=fps,
        width=width,
        height=height,
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
    with _flythrough_jobs_lock:
        if reconstruction_id in _flythrough_jobs:
            raise ValueError(
                f"Flythrough render already running for reconstruction {reconstruction_id}"
            )
        _flythrough_jobs.add(reconstruction_id)

    rec.flythrough_status = "pending"
    rec.flythrough_error = None
    db.commit()
    db.refresh(rec)

    threading.Thread(
        target=_run_flythrough_job,
        args=(reconstruction_id, normalized_keyframes, fps, width, height),
        daemon=True,
    ).start()
    return rec


def _run_flythrough_job(
    reconstruction_id: int,
    keyframes: list[dict],
    fps: int,
    width: int,
    height: int,
) -> None:
    db = SessionLocal()
    try:
        rec = db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).first()
        if rec is None:
            return
        rec.flythrough_status = "running"
        rec.flythrough_error = None
        db.commit()

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
    except Exception as exc:
        db.query(Reconstruction).filter(Reconstruction.id == reconstruction_id).update({
            "flythrough_status": "failed",
            "flythrough_error": str(exc)[:500],
        })
        db.commit()
    finally:
        db.close()
        with _flythrough_jobs_lock:
            _flythrough_jobs.discard(reconstruction_id)


def _load_las_positions(pointcloud_path: Path):
    import laspy
    import numpy as np

    las = laspy.read(pointcloud_path)
    return np.column_stack([las.x, las.y, las.z]).astype(np.float64)


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
        points, _rgb = _read_colmap_points3d(Path(rec.colmap_dir) / "sparse" / "0" / "points3D.txt")
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

    with _comparison_jobs_lock:
        _comparison_jobs.add(comparison.id)

    threading.Thread(
        target=_run_comparison_job,
        args=(comparison.id, voxel_size_m),
        daemon=True,
    ).start()
    return comparison


def _run_comparison_job(comparison_id: int, voxel_size_m: float) -> None:
    db = SessionLocal()
    try:
        comparison = (
            db.query(SessionComparison).filter(SessionComparison.id == comparison_id).first()
        )
        if comparison is None:
            return
        comparison.status = "running"
        comparison.error_msg = None
        db.commit()

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
        comparison.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.query(SessionComparison).filter(SessionComparison.id == comparison_id).update({
            "status": "failed",
            "error_msg": str(exc)[:500],
            "completed_at": datetime.now(timezone.utc),
        })
        db.commit()
    finally:
        db.close()
        with _comparison_jobs_lock:
            _comparison_jobs.discard(comparison_id)


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
