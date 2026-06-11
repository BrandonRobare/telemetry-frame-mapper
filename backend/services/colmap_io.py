"""Pure-numpy loader for COLMAP sparse reconstruction models.

Reads the sparse model that ``_run_colmap`` (backend/services/reconstruction.py)
leaves in ``colmap_dir/sparse/0/``. The COLMAP mapper writes a BIN model there
and ``model_converter`` adds TXT copies alongside it, so :func:`read_model`
prefers BIN and falls back to TXT.

This module deliberately depends on the standard library and numpy only — no
torch, no gsplat, no COLMAP Python bindings, no other ``backend`` imports — so
the splat trainer can consume camera poses and sparse points in any
environment, including CI without GPU or COLMAP installed.

Binary layouts follow COLMAP's documented format
(https://colmap.github.io/format.html). All multi-byte values are
little-endian:

``cameras.bin``
    ``<Q`` camera count, then per camera ``<iiQQ`` (camera_id, model_id,
    width, height) followed by ``num_params`` ``<d`` values. The parameter
    count is derived from the model id.

``images.bin``
    ``<Q`` image count, then per image a ``<idddddddi`` header (image_id,
    qw, qx, qy, qz, tx, ty, tz, camera_id), a null-terminated name, and
    ``<Q`` num_points2D followed by ``24 * num_points2D`` bytes of 2D point
    observations (x ``<d``, y ``<d``, point3D_id ``<Q``), which are skipped.

``points3D.bin``
    ``<Q`` point count, then per point ``<QdddBBBdQ`` (point3D_id, x, y, z,
    r, g, b, reprojection_error, track_length) followed by
    ``8 * track_length`` bytes of track elements, which are skipped.

Quaternions are COLMAP convention: ``wxyz`` order, encoding the world->camera
rotation; ``tvec`` is the world->camera translation.

Only distortion-free camera models are supported (the reconstruction
workspace uses a single PINHOLE camera and never runs ``image_undistorter``):
PINHOLE (model id 1, params fx fy cx cy) and SIMPLE_PINHOLE (model id 0,
params f cx cy). Any other model raises ``RuntimeError`` naming the model.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Supported (distortion-free) COLMAP camera models: model id -> (name, num_params).
_SUPPORTED_CAMERA_MODELS: dict[int, tuple[str, int]] = {
    0: ("SIMPLE_PINHOLE", 3),  # f, cx, cy
    1: ("PINHOLE", 4),  # fx, fy, cx, cy
}

_SUPPORTED_CAMERA_MODEL_NAMES: dict[str, int] = {
    name: num_params for name, num_params in _SUPPORTED_CAMERA_MODELS.values()
}

# Full COLMAP model-id table, used only to name unsupported models in errors.
_CAMERA_MODEL_ID_TO_NAME: dict[int, str] = {
    0: "SIMPLE_PINHOLE",
    1: "PINHOLE",
    2: "SIMPLE_RADIAL",
    3: "RADIAL",
    4: "OPENCV",
    5: "OPENCV_FISHEYE",
    6: "FULL_OPENCV",
    7: "FOV",
    8: "SIMPLE_RADIAL_FISHEYE",
    9: "RADIAL_FISHEYE",
    10: "THIN_PRISM_FISHEYE",
}


@dataclass(frozen=True)
class ColmapCamera:
    camera_id: int
    model: str
    width: int
    height: int
    params: np.ndarray  # PINHOLE: fx fy cx cy; SIMPLE_PINHOLE: f cx cy


@dataclass(frozen=True)
class ColmapImage:
    image_id: int
    qvec: np.ndarray  # wxyz quaternion, world->cam rotation
    tvec: np.ndarray  # world->cam translation
    camera_id: int
    name: str


@dataclass(frozen=True)
class ColmapModel:
    cameras: dict[int, ColmapCamera]
    images: list[ColmapImage]
    points_xyz: np.ndarray  # (P, 3) float64
    points_rgb: np.ndarray  # (P, 3) uint8


def _unsupported_model_error(model: str) -> RuntimeError:
    return RuntimeError(
        f"Unsupported COLMAP camera model: {model}. "
        "Only PINHOLE and SIMPLE_PINHOLE are supported."
    )


def _camera_model_from_id(model_id: int) -> tuple[str, int]:
    """Return (model name, num_params) for a supported model id, else raise."""
    if model_id in _SUPPORTED_CAMERA_MODELS:
        return _SUPPORTED_CAMERA_MODELS[model_id]
    raise _unsupported_model_error(
        _CAMERA_MODEL_ID_TO_NAME.get(model_id, f"model id {model_id}")
    )


def _num_params_for_name(model_name: str) -> int:
    """Return num_params for a supported model name, else raise."""
    if model_name in _SUPPORTED_CAMERA_MODEL_NAMES:
        return _SUPPORTED_CAMERA_MODEL_NAMES[model_name]
    raise _unsupported_model_error(model_name)


def _unpack(fmt: str, data: bytes, offset: int) -> tuple[tuple, int]:
    """Unpack ``fmt`` from ``data`` at ``offset``; return (values, new offset)."""
    values = struct.unpack_from(fmt, data, offset)
    return values, offset + struct.calcsize(fmt)


# ---------------------------------------------------------------------------
# BIN readers
# ---------------------------------------------------------------------------


def read_cameras_bin(path: Path) -> dict[int, ColmapCamera]:
    """Parse ``cameras.bin`` into a dict keyed by camera id."""
    data = path.read_bytes()
    (num_cameras,), offset = _unpack("<Q", data, 0)
    cameras: dict[int, ColmapCamera] = {}
    for _ in range(num_cameras):
        (camera_id, model_id, width, height), offset = _unpack("<iiQQ", data, offset)
        model_name, num_params = _camera_model_from_id(model_id)
        params = np.frombuffer(data, dtype="<f8", count=num_params, offset=offset)
        offset += 8 * num_params
        cameras[camera_id] = ColmapCamera(
            camera_id=camera_id,
            model=model_name,
            width=int(width),
            height=int(height),
            params=params.astype(np.float64),
        )
    return cameras


def read_images_bin(path: Path) -> list[ColmapImage]:
    """Parse ``images.bin``; per-image 2D point observations are skipped."""
    data = path.read_bytes()
    (num_images,), offset = _unpack("<Q", data, 0)
    images: list[ColmapImage] = []
    for _ in range(num_images):
        fields, offset = _unpack("<idddddddi", data, offset)
        image_id = int(fields[0])
        qvec = np.array(fields[1:5], dtype=np.float64)
        tvec = np.array(fields[5:8], dtype=np.float64)
        camera_id = int(fields[8])
        name_end = data.index(b"\x00", offset)
        name = data[offset:name_end].decode("utf-8")
        offset = name_end + 1
        (num_points2d,), offset = _unpack("<Q", data, offset)
        offset += 24 * num_points2d  # skip (x: d, y: d, point3D_id: Q) per 2D point
        images.append(
            ColmapImage(image_id=image_id, qvec=qvec, tvec=tvec, camera_id=camera_id, name=name)
        )
    return images


def read_points3d_bin(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse ``points3D.bin`` into (xyz float64 (P,3), rgb uint8 (P,3)).

    Reprojection errors and track elements are skipped.
    """
    data = path.read_bytes()
    (num_points,), offset = _unpack("<Q", data, 0)
    xyz = np.empty((num_points, 3), dtype=np.float64)
    rgb = np.empty((num_points, 3), dtype=np.uint8)
    for i in range(num_points):
        fields, offset = _unpack("<QdddBBBdQ", data, offset)
        xyz[i] = fields[1:4]
        rgb[i] = fields[4:7]
        track_length = int(fields[8])
        offset += 8 * track_length  # skip (image_id: i, point2D_idx: i) per track element
    return xyz, rgb


# ---------------------------------------------------------------------------
# TXT readers (line conventions mirror _read_colmap_points3d and
# _store_reprojection_errors in backend/services/reconstruction.py)
# ---------------------------------------------------------------------------


def read_cameras_txt(path: Path) -> dict[int, ColmapCamera]:
    """Parse ``cameras.txt`` (CAMERA_ID MODEL WIDTH HEIGHT PARAMS[])."""
    cameras: dict[int, ColmapCamera] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        camera_id = int(parts[0])
        model_name = parts[1]
        num_params = _num_params_for_name(model_name)
        params = np.array([float(p) for p in parts[4 : 4 + num_params]], dtype=np.float64)
        cameras[camera_id] = ColmapCamera(
            camera_id=camera_id,
            model=model_name,
            width=int(parts[2]),
            height=int(parts[3]),
            params=params,
        )
    return cameras


def read_images_txt(path: Path) -> list[ColmapImage]:
    """Parse ``images.txt`` (two lines per image; the 2D point line is skipped)."""
    images: list[ColmapImage] = []
    raw_lines = [line for line in path.read_text().splitlines() if not line.startswith("#")]
    i = 0
    while i < len(raw_lines):
        header = raw_lines[i].strip()
        i += 1
        if not header:
            continue
        parts = header.split()
        images.append(
            ColmapImage(
                image_id=int(parts[0]),
                qvec=np.array([float(v) for v in parts[1:5]], dtype=np.float64),
                tvec=np.array([float(v) for v in parts[5:8]], dtype=np.float64),
                camera_id=int(parts[8]),
                name=parts[9],
            )
        )
        i += 1  # skip the POINTS2D[] line that follows each image header
    return images


def read_points3d_txt(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse ``points3D.txt`` into (xyz float64 (P,3), rgb uint8 (P,3))."""
    xyz: list[list[float]] = []
    rgb: list[list[int]] = []
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        xyz.append([float(parts[1]), float(parts[2]), float(parts[3])])
        rgb.append([int(parts[4]), int(parts[5]), int(parts[6])])
    return (
        np.array(xyz, dtype=np.float64).reshape(-1, 3),
        np.array(rgb, dtype=np.uint8).reshape(-1, 3),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_model(sparse_dir: Path) -> ColmapModel:
    """Load a COLMAP sparse model from ``sparse_dir``, preferring BIN over TXT.

    The mapper writes BIN and ``model_converter`` adds TXT in place, so a
    finished workspace usually has both; BIN is authoritative. Raises
    ``RuntimeError`` if neither format is present.
    """
    if (sparse_dir / "cameras.bin").exists():
        cameras = read_cameras_bin(sparse_dir / "cameras.bin")
        images = read_images_bin(sparse_dir / "images.bin")
        points_xyz, points_rgb = read_points3d_bin(sparse_dir / "points3D.bin")
    elif (sparse_dir / "cameras.txt").exists():
        cameras = read_cameras_txt(sparse_dir / "cameras.txt")
        images = read_images_txt(sparse_dir / "images.txt")
        points_xyz, points_rgb = read_points3d_txt(sparse_dir / "points3D.txt")
    else:
        raise RuntimeError(f"COLMAP sparse model not found in {sparse_dir}")
    return ColmapModel(
        cameras=cameras, images=images, points_xyz=points_xyz, points_rgb=points_rgb
    )


def qvec_to_rotmat(qvec: np.ndarray) -> np.ndarray:
    """Convert a wxyz quaternion to a 3x3 rotation matrix (float64).

    COLMAP stores quaternions normalized, but normalize defensively so a
    hand-built or round-tripped qvec still yields a proper rotation.
    """
    q = np.asarray(qvec, dtype=np.float64)
    w, x, y, z = q / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def world_to_cam_matrix(image: ColmapImage) -> np.ndarray:
    """Return the 4x4 world->camera view matrix for ``image``.

    Top-left 3x3 is the rotation from ``qvec``; the last column holds
    ``tvec``: ``X_cam = R @ X_world + t``.
    """
    viewmat = np.eye(4, dtype=np.float64)
    viewmat[:3, :3] = qvec_to_rotmat(image.qvec)
    viewmat[:3, 3] = np.asarray(image.tvec, dtype=np.float64)
    return viewmat
