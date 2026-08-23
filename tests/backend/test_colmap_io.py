from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from backend.services.colmap_io import (
    ColmapImage,
    _pick_best_submodel,
    qvec_to_rotmat,
    read_cameras_bin,
    read_images_bin,
    read_model,
    read_points3d_bin,
    world_to_cam_matrix,
)

# ---------------------------------------------------------------------------
# Inline BIN fixture builders (COLMAP binary layout, little-endian)
# ---------------------------------------------------------------------------

_INVALID_POINT3D_ID = 2**64 - 1  # COLMAP kInvalidPoint3DId


def _cameras_bin(cameras: list[tuple[int, int, int, int, list[float]]]) -> bytes:
    """cameras: (camera_id, model_id, width, height, params)."""
    chunks = [struct.pack("<Q", len(cameras))]
    for camera_id, model_id, width, height, params in cameras:
        chunks.append(struct.pack("<iiQQ", camera_id, model_id, width, height))
        chunks.append(struct.pack(f"<{len(params)}d", *params))
    return b"".join(chunks)


def _images_bin(
    images: list[tuple[int, list[float], list[float], int, str, list[tuple[float, float, int]]]],
) -> bytes:
    """images: (image_id, qvec wxyz, tvec, camera_id, name, points2d (x, y, point3d_id))."""
    chunks = [struct.pack("<Q", len(images))]
    for image_id, qvec, tvec, camera_id, name, points2d in images:
        chunks.append(struct.pack("<idddddddi", image_id, *qvec, *tvec, camera_id))
        chunks.append(name.encode("utf-8") + b"\x00")
        chunks.append(struct.pack("<Q", len(points2d)))
        for x, y, point3d_id in points2d:
            chunks.append(struct.pack("<ddQ", x, y, point3d_id))
    return b"".join(chunks)


def _points3d_bin(
    points: list[tuple[int, list[float], list[int], float, list[tuple[int, int]]]],
) -> bytes:
    """points: (point3d_id, xyz, rgb, error, track (image_id, point2d_idx))."""
    chunks = [struct.pack("<Q", len(points))]
    for point3d_id, xyz, rgb, error, track in points:
        chunks.append(struct.pack("<QdddBBBdQ", point3d_id, *xyz, *rgb, error, len(track)))
        for image_id, point2d_idx in track:
            chunks.append(struct.pack("<ii", image_id, point2d_idx))
    return b"".join(chunks)


_QVEC = [0.7071067811865476, 0.0, 0.0, 0.7071067811865476]  # 90 deg about +z, wxyz
_TVEC = [0.5, -0.25, 2.0]


def test_pick_best_submodel_prefers_the_most_registered_images(tmp_path):
    """Fragmented reconstructions consistently select their largest model."""
    sparse = tmp_path / "sparse"
    _write_txt_model(sparse / "0")
    _write_txt_model(sparse / "1")
    images = (sparse / "1" / "images.txt").read_text()
    (sparse / "1" / "images.txt").write_text(images + images.splitlines()[3] + "\n\n")

    assert _pick_best_submodel(sparse) == sparse / "1"


def test_pick_best_submodel_prefers_largest_bin_only_model(tmp_path):
    """Fresh mapper output is BIN-only before model_converter runs."""
    sparse = tmp_path / "sparse"
    model_zero = sparse / "0"
    model_one = sparse / "1"
    model_zero.mkdir(parents=True)
    model_one.mkdir(parents=True)
    (model_zero / "images.bin").write_bytes(_images_bin([(1, _QVEC, _TVEC, 1, "a.jpg", [])]))
    (model_one / "images.bin").write_bytes(
        _images_bin(
            [
                (1, _QVEC, _TVEC, 1, "a.jpg", []),
                (2, _QVEC, _TVEC, 1, "b.jpg", []),
            ]
        )
    )

    assert _pick_best_submodel(sparse) == model_one


def _write_bin_model(sparse_dir: Path) -> None:
    sparse_dir.mkdir(parents=True, exist_ok=True)
    (sparse_dir / "cameras.bin").write_bytes(
        _cameras_bin([(1, 1, 1920, 1080, [1000.0, 1000.0, 960.0, 540.0])])
    )
    (sparse_dir / "images.bin").write_bytes(
        _images_bin(
            [
                (1, _QVEC, _TVEC, 1, "frame_000001.jpg", [(10.0, 20.0, 7)]),
                (2, [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1, "frame_000002.jpg", []),
            ]
        )
    )
    (sparse_dir / "points3D.bin").write_bytes(
        _points3d_bin(
            [
                (7, [1.5, -2.0, 3.25], [255, 128, 64], 0.83, [(1, 0), (2, 1)]),
                (9, [-4.0, 5.5, 0.125], [0, 200, 30], 1.2, [(1, 3)]),
            ]
        )
    )


def _write_txt_model(sparse_dir: Path) -> None:
    """TXT model equivalent to _write_bin_model (COLMAP TXT conventions)."""
    sparse_dir.mkdir(parents=True, exist_ok=True)
    (sparse_dir / "cameras.txt").write_text(
        "# Camera list with one line of data per camera:\n"
        "#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n"
        "1 PINHOLE 1920 1080 1000.0 1000.0 960.0 540.0\n"
    )
    qw, qx, qy, qz = _QVEC
    tx, ty, tz = _TVEC
    (sparse_dir / "images.txt").write_text(
        "# Image list with two lines of data per image:\n"
        "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n"
        "#   POINTS2D[] as (X, Y, POINT3D_ID)\n"
        f"1 {qw} {qx} {qy} {qz} {tx} {ty} {tz} 1 frame_000001.jpg\n"
        "10.0 20.0 7\n"
        "2 1.0 0.0 0.0 0.0 0.0 0.0 1.0 1 frame_000002.jpg\n"
        "\n"
    )
    (sparse_dir / "points3D.txt").write_text(
        "# 3D point list with one line of data per point:\n"
        "#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n"
        "7 1.5 -2.0 3.25 255 128 64 0.83 1 0 2 1\n"
        "9 -4.0 5.5 0.125 0 200 30 1.2 1 3\n"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_read_cameras_bin_pinhole(tmp_path):
    path = tmp_path / "cameras.bin"
    path.write_bytes(
        _cameras_bin(
            [
                (1, 1, 1920, 1080, [1000.0, 1001.0, 960.0, 540.0]),  # PINHOLE
                (2, 0, 640, 480, [500.0, 320.0, 240.0]),  # SIMPLE_PINHOLE
            ]
        )
    )

    cameras = read_cameras_bin(path)

    assert set(cameras) == {1, 2}
    pinhole = cameras[1]
    assert pinhole.model == "PINHOLE"
    assert (pinhole.width, pinhole.height) == (1920, 1080)
    np.testing.assert_allclose(pinhole.params, [1000.0, 1001.0, 960.0, 540.0])
    simple = cameras[2]
    assert simple.model == "SIMPLE_PINHOLE"
    np.testing.assert_allclose(simple.params, [500.0, 320.0, 240.0])


def test_read_images_bin_quaternion_and_name(tmp_path):
    path = tmp_path / "images.bin"
    points2d = [(10.0, 20.0, 7), (30.0, 40.0, _INVALID_POINT3D_ID)]
    path.write_bytes(
        _images_bin(
            [
                (3, _QVEC, _TVEC, 1, "frame_000003.jpg", points2d),
                (4, [1.0, 0.0, 0.0, 0.0], [1.0, 2.0, 3.0], 1, "frame_000004.jpg", []),
            ]
        )
    )

    images = read_images_bin(path)

    assert [img.image_id for img in images] == [3, 4]
    first = images[0]
    np.testing.assert_allclose(first.qvec, _QVEC)
    np.testing.assert_allclose(first.tvec, _TVEC)
    assert first.camera_id == 1
    assert first.name == "frame_000003.jpg"
    # The second image parses correctly only if the first image's 2D point
    # block (24 bytes per observation) was skipped exactly.
    second = images[1]
    np.testing.assert_allclose(second.qvec, [1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(second.tvec, [1.0, 2.0, 3.0])
    assert second.name == "frame_000004.jpg"


def test_read_points3d_bin_xyz_rgb_skips_track(tmp_path):
    path = tmp_path / "points3D.bin"
    path.write_bytes(
        _points3d_bin(
            [
                (7, [1.5, -2.0, 3.25], [255, 128, 64], 0.83, [(1, 0), (2, 1), (3, 5)]),
                (9, [-4.0, 5.5, 0.125], [0, 200, 30], 1.2, [(1, 3)]),
            ]
        )
    )

    xyz, rgb = read_points3d_bin(path)

    assert xyz.shape == (2, 3) and xyz.dtype == np.float64
    assert rgb.shape == (2, 3) and rgb.dtype == np.uint8
    # The second point parses correctly only if the first point's track
    # (8 bytes per element) was skipped exactly.
    np.testing.assert_allclose(xyz, [[1.5, -2.0, 3.25], [-4.0, 5.5, 0.125]])
    np.testing.assert_array_equal(rgb, [[255, 128, 64], [0, 200, 30]])


def test_read_model_prefers_bin_over_txt(tmp_path):
    sparse = tmp_path / "sparse" / "0"
    _write_bin_model(sparse)
    _write_txt_model(sparse)
    # Make the TXT camera disagree with BIN so the source is detectable.
    (sparse / "cameras.txt").write_text("5 SIMPLE_PINHOLE 100 100 50.0 50.0 50.0\n")

    model = read_model(sparse)

    assert set(model.cameras) == {1}
    assert model.cameras[1].model == "PINHOLE"
    assert (model.cameras[1].width, model.cameras[1].height) == (1920, 1080)


def test_read_model_txt_fallback_matches_bin(tmp_path):
    bin_dir = tmp_path / "bin" / "sparse" / "0"
    txt_dir = tmp_path / "txt" / "sparse" / "0"
    _write_bin_model(bin_dir)
    _write_txt_model(txt_dir)

    from_bin = read_model(bin_dir)
    from_txt = read_model(txt_dir)

    assert set(from_bin.cameras) == set(from_txt.cameras)
    for cam_id, bin_cam in from_bin.cameras.items():
        txt_cam = from_txt.cameras[cam_id]
        assert (bin_cam.model, bin_cam.width, bin_cam.height) == (
            txt_cam.model,
            txt_cam.width,
            txt_cam.height,
        )
        np.testing.assert_allclose(bin_cam.params, txt_cam.params)
    assert len(from_bin.images) == len(from_txt.images) == 2
    for bin_img, txt_img in zip(from_bin.images, from_txt.images, strict=True):
        assert (bin_img.image_id, bin_img.camera_id, bin_img.name) == (
            txt_img.image_id,
            txt_img.camera_id,
            txt_img.name,
        )
        np.testing.assert_allclose(bin_img.qvec, txt_img.qvec)
        np.testing.assert_allclose(bin_img.tvec, txt_img.tvec)
    np.testing.assert_allclose(from_bin.points_xyz, from_txt.points_xyz)
    np.testing.assert_array_equal(from_bin.points_rgb, from_txt.points_rgb)


def test_read_model_missing_raises_runtime_error(tmp_path):
    sparse = tmp_path / "sparse" / "0"
    sparse.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="COLMAP sparse model not found"):
        read_model(sparse)


def test_unsupported_camera_model_raises(tmp_path):
    bin_path = tmp_path / "cameras.bin"
    # Model id 4 = OPENCV (8 params): unsupported because it has distortion.
    bin_path.write_bytes(_cameras_bin([(1, 4, 1920, 1080, [1.0] * 8)]))
    with pytest.raises(RuntimeError, match="OPENCV"):
        read_cameras_bin(bin_path)

    sparse = tmp_path / "sparse" / "0"
    _write_txt_model(sparse)
    (sparse / "cameras.txt").write_text("1 RADIAL 1920 1080 1000.0 960.0 540.0 0.1 0.01\n")
    with pytest.raises(RuntimeError, match="RADIAL"):
        read_model(sparse)


def test_qvec_to_rotmat_identity_and_known_rotation():
    np.testing.assert_allclose(qvec_to_rotmat(np.array([1.0, 0.0, 0.0, 0.0])), np.eye(3))

    # 90 degrees about +z (wxyz): maps x->y, y->-x.
    rot = qvec_to_rotmat(np.array(_QVEC))
    expected = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    np.testing.assert_allclose(rot, expected, atol=1e-12)

    # world_to_cam_matrix embeds the same rotation plus tvec in a 4x4 viewmat.
    image = ColmapImage(
        image_id=1,
        qvec=np.array(_QVEC),
        tvec=np.array(_TVEC),
        camera_id=1,
        name="frame_000001.jpg",
    )
    viewmat = world_to_cam_matrix(image)
    assert viewmat.shape == (4, 4)
    np.testing.assert_allclose(viewmat[:3, :3], expected, atol=1e-12)
    np.testing.assert_allclose(viewmat[:3, 3], _TVEC)
    np.testing.assert_allclose(viewmat[3], [0.0, 0.0, 0.0, 1.0])
