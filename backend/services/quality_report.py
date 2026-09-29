"""Quality report aggregation for reconstruction scorecard, GCP accuracy, and
held-out checkpoint validation.

All math is deterministic; no AI/ML estimation.  The GCP accuracy report
operates on a local COLMAP geo-transform (scale + rotation + translation
into a UTM-like local coordinate system) and does *not* assume geographic
coordinates — it matches the semantics of the stored ``geo_transform``
produced by ``backend.services.reconstruction._extract_geo_transform``.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------


class SurfaceExtractionError(Exception):
    """A surface artifact exists but its points could not be read.

    Kept distinct from a surface that reads cleanly and holds no points, which
    the extractors report by returning an empty list.
    """


@dataclass(frozen=True)
class SurveyedPoint:
    """A surveyed control or checkpoint with local 3-D coordinates.

    For GCP accuracy reports, ``reconstructed_*`` stores the corresponding
    reconstructed/control-point coordinate so residuals compare paired
    observations instead of measuring distance from the transform origin.
    """

    label: str
    x: float
    y: float
    z: float
    reconstructed_x: float | None = None
    reconstructed_y: float | None = None
    reconstructed_z: float | None = None


@dataclass
class GcpResidual:
    label: str
    dx: float
    dy: float
    dz: float
    distance_3d: float


@dataclass
class CheckpointValidation:
    label: str
    distance_m: float
    surface_point: str | None = None  # "x,y,z" of nearest surface point, or None


# ---------------------------------------------------------------------------
#  Quality scorecard (issue #292)
# ---------------------------------------------------------------------------


def build_quality_scorecard(
    rec: Any,
    frames: list[Any],
    training_metrics: list[dict] | None,
    coverage_gaps: list[dict] | None,
) -> dict:
    """Aggregate reconstruction metrics into a JSON-exportable scorecard.

    Parameters
    ----------
    rec:
        A ``Reconstruction`` ORM row (must have ``frames_used``,
        ``frames_registered``, ``gaussian_count``, ``psnr``, ``ssim``).
    frames:
        ``ReconstructionFrame`` rows for this reconstruction.
    training_metrics:
        Parsed ``training_metrics`` JSON list, or *None*.
    coverage_gaps:
        Coverage-gap cell list, or *None*.
    """
    registered = rec.frames_registered or 0
    total_frames = rec.frames_used or 0
    registration_completeness_pct = (
        round(registered / total_frames * 100, 1) if total_frames > 0 else 0.0
    )

    # Reprojection error (from COLMAP, stored per-frame)
    errors_px = [f.colmap_error_px for f in frames if f.colmap_error_px is not None]
    reprojection: dict = {
        "mean_px": round(mean(errors_px), 3) if errors_px else None,
        "std_px": round(stdev(errors_px), 3) if len(errors_px) > 1 else None,
        "min_px": round(min(errors_px), 3) if errors_px else None,
        "max_px": round(max(errors_px), 3) if errors_px else None,
        "frame_count_with_data": len(errors_px),
    }

    # PSNR / SSIM trend
    quality: dict = {
        "psnr_final": rec.psnr,
        "ssim_final": rec.ssim,
        "training_metric_points": len(training_metrics) if training_metrics else 0,
    }
    if training_metrics and len(training_metrics) > 1:
        psnr_values = [p["psnr"] for p in training_metrics if "psnr" in p]
        ssim_values = [p["ssim"] for p in training_metrics if "ssim" in p]
        quality["psnr_trend"] = {
            "start": round(psnr_values[0], 3),
            "end": round(psnr_values[-1], 3),
            "delta": round(psnr_values[-1] - psnr_values[0], 3),
        }
        if ssim_values:
            quality["ssim_trend"] = {
                "start": round(ssim_values[0], 6),
                "end": round(ssim_values[-1], 6),
                "delta": round(ssim_values[-1] - ssim_values[0], 6),
            }

    # Coverage gaps
    gap_summary: dict | None = None
    if coverage_gaps:
        levels: dict[str, int] = {}
        for cell in coverage_gaps:
            level = cell.get("level", "unknown")
            levels[level] = levels.get(level, 0) + 1
        gap_summary = {
            "total_gaps": len(coverage_gaps),
            "by_level": levels,
        }
        if coverage_gaps:
            sizes = [c["size"] for c in coverage_gaps if "size" in c]
            if sizes:
                gap_summary["voxel_size_m"] = sizes[0]

    return {
        "reconstruction_id": rec.id,
        "frame_counts": {
            "frames_used": total_frames,
            "frames_registered": registered,
            "registration_completeness_pct": registration_completeness_pct,
        },
        "density": {
            "gaussian_count": rec.gaussian_count,
        },
        "reprojection_error": reprojection,
        "quality": quality,
        "coverage_gaps": gap_summary,
    }


# ---------------------------------------------------------------------------
#  GCP accuracy report (issue #287)
# ---------------------------------------------------------------------------


def compute_gcp_accuracy(
    geo_transform: dict,
    survey_points: list[SurveyedPoint],
) -> dict:
    """Compute paired GCP residuals and RMSE.

    Each point must include surveyed coordinates (``x/y/z``) and the matching
    reconstructed/control-point coordinates (``reconstructed_x/y/z``).  RMSE is
    computed from those paired observations, which is the client-facing GCP
    accuracy metric requested by #287.
    """
    residuals: list[GcpResidual] = []
    dx_list: list[float] = []
    dy_list: list[float] = []
    dz_list: list[float] = []
    d3d_list: list[float] = []

    for sp in survey_points:
        missing = [
            name
            for name, value in (
                ("reconstructed_x", sp.reconstructed_x),
                ("reconstructed_y", sp.reconstructed_y),
                ("reconstructed_z", sp.reconstructed_z),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "GCP accuracy requires paired reconstructed coordinates; "
                f"missing {', '.join(missing)} for {sp.label}"
            )

        dx = float(sp.x - sp.reconstructed_x)
        dy = float(sp.y - sp.reconstructed_y)
        dz = float(sp.z - sp.reconstructed_z)
        d3d = math.sqrt(dx * dx + dy * dy + dz * dz)
        residuals.append(
            GcpResidual(
                label=sp.label,
                dx=round(dx, 4),
                dy=round(dy, 4),
                dz=round(dz, 4),
                distance_3d=round(d3d, 4),
            )
        )
        dx_list.append(dx)
        dy_list.append(dy)
        dz_list.append(dz)
        d3d_list.append(d3d)

    rmse_x = _rmse(dx_list) if dx_list else None
    rmse_y = _rmse(dy_list) if dy_list else None
    rmse_z = _rmse(dz_list) if dz_list else None
    rmse_3d = _rmse(d3d_list) if d3d_list else None

    return {
        "geo_transform": geo_transform,
        "point_count": len(survey_points),
        "rmse": {
            "x_m": round(rmse_x, 4) if rmse_x is not None else None,
            "y_m": round(rmse_y, 4) if rmse_y is not None else None,
            "z_m": round(rmse_z, 4) if rmse_z is not None else None,
            "3d_m": round(rmse_3d, 4) if rmse_3d is not None else None,
        },
        "residuals": [
            {
                "label": r.label,
                "dx_m": r.dx,
                "dy_m": r.dy,
                "dz_m": r.dz,
                "distance_3d_m": r.distance_3d,
            }
            for r in residuals
        ],
    }


# ---------------------------------------------------------------------------
#  Held-out checkpoint validation (issue #294)
# ---------------------------------------------------------------------------


def validate_held_out_checkpoints(
    rec: Any,
    survey_points: list[SurveyedPoint],
) -> dict:
    """Report the nearest-surface distance for each independent checkpoint.

    Preference order: mesh, splat, pointcloud.  When the check cannot run the
    result has ``available: False``, a 422-eligible ``reason`` and a ``status``:
    ``unavailable`` (no surface artifact on disk), ``failed`` (the artifact could
    not be read; ``error`` names the parser error) or ``empty`` (the artifact
    read cleanly but holds no points).
    """
    candidates = (
        ("mesh", rec.mesh_glb_path, _extract_mesh_surface_points),
        ("splat", rec.splat_path, _extract_splat_surface_points),
        ("pointcloud", rec.pointcloud_path, _extract_pointcloud_surface_points),
    )
    selected = next(
        (entry for entry in candidates if entry[1] and Path(entry[1]).exists()), None
    )
    if selected is None:
        return {
            "available": False,
            "status": "unavailable",
            "reason": (
                "No surface source (mesh, splat, or point cloud) is available "
                "for this reconstruction."
            ),
        }

    source, surface_path, extract = selected
    surface_name = Path(surface_path).name
    try:
        points = extract(surface_path)
    except SurfaceExtractionError as exc:
        logger.warning(
            "Checkpoint validation could not read the %s surface at %s",
            source,
            surface_path,
            exc_info=True,
        )
        return {
            "available": False,
            "status": "failed",
            "source": source,
            "error": str(exc),
            "reason": f"Could not read the {source} surface ({surface_name}): {exc}",
        }
    if not points:
        return {
            "available": False,
            "status": "empty",
            "source": source,
            "reason": f"The {source} surface ({surface_name}) contains no points.",
        }

    results: list[CheckpointValidation] = []
    np_points = np.array(points, dtype=np.float64)

    for sp in survey_points:
        query = np.array([sp.x, sp.y, sp.z], dtype=np.float64)
        distances = np.linalg.norm(np_points - query, axis=1)
        idx = int(np.argmin(distances))
        dist_m = float(distances[idx])
        # Format the nearest surface point for traceability
        nearest = np_points[idx]
        surface_str = f"{nearest[0]:.4f},{nearest[1]:.4f},{nearest[2]:.4f}"
        results.append(
            CheckpointValidation(
                label=sp.label,
                distance_m=round(dist_m, 4),
                surface_point=surface_str,
            )
        )

    distances_m = [r.distance_m for r in results]
    return {
        "available": True,
        "source": source,
        "point_count": len(survey_points),
        "surface_point_count": len(points),
        "summary": {
            "min_m": round(min(distances_m), 4) if distances_m else None,
            "max_m": round(max(distances_m), 4) if distances_m else None,
            "mean_m": round(mean(distances_m), 4) if distances_m else None,
            "rmse_m": round(_rmse(distances_m), 4) if distances_m else None,
        },
        "checkpoints": [
            {
                "label": r.label,
                "distance_m": r.distance_m,
                "nearest_surface_point": r.surface_point,
            }
            for r in results
        ],
    }


# ---------------------------------------------------------------------------
#  Surface extraction helpers
# ---------------------------------------------------------------------------


def _describe_read_error(exc: Exception, path: str) -> str:
    """Name a surface read failure without the artifact's server-side directory.

    The description ends up in an API response; the full path and traceback go
    to the log instead.
    """
    if isinstance(exc, OSError) and exc.strerror:
        return exc.strerror
    message = str(exc) or type(exc).__name__
    for form in {str(path), str(Path(path))}:
        message = message.replace(form, Path(path).name)
    return f"{type(exc).__name__}: {message}"


def _extract_splat_surface_points(splat_path: str) -> list[tuple[float, float, float]]:
    """Extract Gaussian mean positions from a PLY splat file.

    Raises :class:`SurfaceExtractionError` when the PLY cannot be read.
    """
    from backend.services.ply_io import read_3dgs_ply

    try:
        cloud = read_3dgs_ply(Path(splat_path))
    except Exception as exc:
        raise SurfaceExtractionError(_describe_read_error(exc, splat_path)) from exc
    means = cloud.means  # (N, 3) float32
    if means.shape[0] > 100_000:
        # Down-sample for performance
        indices = np.linspace(0, means.shape[0] - 1, 100_000, dtype=np.int64)
        means = means[indices]
    return [(float(m[0]), float(m[1]), float(m[2])) for m in means.tolist()]


def _extract_mesh_surface_points(mesh_path: str) -> list[tuple[float, float, float]]:
    """Extract vertex positions from a GLB mesh.

    Reads the GLB binary layout directly to avoid bringing in a heavy GLTF
    library.  Raises :class:`SurfaceExtractionError` when the file cannot be
    read or parsed; returns an empty list only for a well-formed mesh that has
    no vertex positions.
    """
    try:
        positions = _parse_glb_vertex_positions(Path(mesh_path).read_bytes())
    except SurfaceExtractionError:
        raise
    except Exception as exc:
        raise SurfaceExtractionError(_describe_read_error(exc, mesh_path)) from exc
    # Down-sample to 100k max
    if len(positions) > 100_000:
        step = max(1, len(positions) // 100_000)
        positions = positions[::step]
    return positions


def _extract_pointcloud_surface_points(
    pointcloud_path: str,
) -> list[tuple[float, float, float]]:
    """Extract point positions from a LAS point cloud.

    Raises :class:`SurfaceExtractionError` when laspy is not installed or the
    file cannot be read; returns an empty list for a readable, empty cloud.
    """
    try:
        import laspy
    except ImportError as exc:
        raise SurfaceExtractionError(
            "reading LAS point clouds requires the optional laspy package; install it "
            "from a source checkout with: uv sync --group backend --group reconstruction"
        ) from exc
    try:
        las = laspy.read(pointcloud_path)
        x = las.x
        y = las.y
        z = las.z
    except Exception as exc:
        raise SurfaceExtractionError(_describe_read_error(exc, pointcloud_path)) from exc
    n = min(len(x), 100_000)
    if n == 0:
        return []
    indices = np.linspace(0, len(x) - 1, n, dtype=np.int64)
    return [(float(x[i]), float(y[i]), float(z[i])) for i in indices]


def _parse_glb_vertex_positions(data: bytes) -> list[tuple[float, float, float]]:
    """Minimal GLB parser: extract vertex positions from the first POSITION accessor.

    Returns an empty list only when the file is well formed and has no vertex
    positions (no mesh primitive with POSITION, or a zero-count accessor).
    Anything unreadable raises :class:`SurfaceExtractionError` naming the problem.
    """
    import struct

    if data[:4] != b"glTF":
        raise SurfaceExtractionError("not a GLB file (missing glTF magic)")
    if len(data) < 20:
        raise SurfaceExtractionError(f"GLB header is truncated ({len(data)} bytes)")

    # Skip 12-byte header to get first chunk
    # GLB: magic(4) version(4) length(4) chunkLength(4) chunkType(4)
    json_length = struct.unpack_from("<I", data, 12)[0]
    if 20 + json_length > len(data):
        raise SurfaceExtractionError("GLB JSON chunk is truncated")
    json_bytes = data[20 : 20 + json_length]
    try:
        gltf = json.loads(json_bytes)
    except ValueError as exc:  # JSONDecodeError or UnicodeDecodeError
        raise SurfaceExtractionError(f"GLB JSON chunk is not valid JSON: {exc}") from exc
    if not isinstance(gltf, dict):
        raise SurfaceExtractionError("GLB JSON chunk is not a glTF object")

    # Find first primitive with a POSITION attribute
    position_accessor_idx = None
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attrs = primitive.get("attributes", {})
            if "POSITION" in attrs:
                position_accessor_idx = attrs["POSITION"]
                break
        if position_accessor_idx is not None:
            break

    if position_accessor_idx is None:
        return []

    accessors = gltf.get("accessors", [])
    if not isinstance(position_accessor_idx, int) or not (
        0 <= position_accessor_idx < len(accessors)
    ):
        raise SurfaceExtractionError(f"POSITION accessor {position_accessor_idx!r} does not exist")
    accessor = accessors[position_accessor_idx]

    count = accessor.get("count", 0)
    component_type = accessor.get("componentType", 5126)  # FLOAT default
    type_str = accessor.get("type", "VEC3")
    if component_type != 5126 or type_str != "VEC3":
        raise SurfaceExtractionError(
            f"unsupported POSITION accessor (componentType {component_type}, type {type_str}); "
            "only float VEC3 positions can be read"
        )
    if count == 0:
        return []

    buffer_views = gltf.get("bufferViews", [])
    buffer_view_idx = accessor.get("bufferView")
    if not isinstance(buffer_view_idx, int) or not (0 <= buffer_view_idx < len(buffer_views)):
        raise SurfaceExtractionError("POSITION accessor has no readable bufferView")
    buffer_view = buffer_views[buffer_view_idx]

    # Find binary chunk
    bin_offset = 20 + json_length
    # The binary chunk has: chunkLength(4) chunkType(4) bytes...
    if bin_offset + 8 > len(data):
        raise SurfaceExtractionError("GLB has no BIN chunk holding the vertex data")
    bin_data = data[bin_offset + 8 :]

    byte_offset = buffer_view.get("byteOffset", 0)
    byte_length = buffer_view.get("byteLength", 0)
    if byte_offset + byte_length > len(bin_data):
        raise SurfaceExtractionError(
            f"GLB BIN chunk is truncated: the POSITION bufferView needs "
            f"{byte_offset + byte_length} bytes, the chunk has {len(bin_data)}"
        )
    view_data = bin_data[byte_offset : byte_offset + byte_length]

    # Honour the accessor offset and an interleaved (strided) buffer view.
    start = accessor.get("byteOffset", 0)
    stride = buffer_view.get("byteStride") or 12
    needed = start + (count - 1) * stride + 12
    if needed > len(view_data):
        raise SurfaceExtractionError(
            f"GLB vertex data is truncated: {count} positions need {needed} bytes, "
            f"the bufferView has {len(view_data)}"
        )

    positions: list[tuple[float, float, float]] = []
    fmt = "<3f"
    for i in range(count):
        x, y, z = struct.unpack_from(fmt, view_data, start + i * stride)
        positions.append((float(x), float(y), float(z)))
    return positions


# ---------------------------------------------------------------------------
#  Shared helpers
# ---------------------------------------------------------------------------


def _rmse(values: list[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


def parse_surveyed_points_3d(
    items: list[dict],
) -> list[SurveyedPoint]:
    """Parse a list of {label, x, y, z} dicts into SurveyedPoint objects.

    The dict keys should match the local coordinate system — typically
    already converted from WGS84 to the reconstruction's UTM zone.
    """
    points: list[SurveyedPoint] = []
    for i, item in enumerate(items):
        label = str(item.get("label") or f"point_{i}")
        x = float(item["x"])
        y = float(item["y"])
        z = float(item["z"])
        reconstructed_x = (
            float(item["reconstructed_x"]) if item.get("reconstructed_x") is not None else None
        )
        reconstructed_y = (
            float(item["reconstructed_y"]) if item.get("reconstructed_y") is not None else None
        )
        reconstructed_z = (
            float(item["reconstructed_z"]) if item.get("reconstructed_z") is not None else None
        )
        points.append(
            SurveyedPoint(
                label=label,
                x=x,
                y=y,
                z=z,
                reconstructed_x=reconstructed_x,
                reconstructed_y=reconstructed_y,
                reconstructed_z=reconstructed_z,
            )
        )
    return points
