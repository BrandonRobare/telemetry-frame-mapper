"""Read, write, and prune Gaussian-splat PLY files in the INRIA 3DGS layout.

This is the exact binary layout produced by the original INRIA 3D Gaussian
Splatting trainer and consumed by ``@mkkellogg/gaussian-splats-3d`` (the
frontend viewer), the LAS export (``_load_ply_positions_and_colors``), and the
coverage-gap analysis (``_compute_coverage_gaps``) in
``backend/services/reconstruction.py``. The layout written here is a hard
compatibility contract — see V1_RELEASE_CHECKLIST.md task T2.

Conventions baked into the format:

- One ``element vertex N`` with all-``float`` properties, in exactly this
  order: ``x y z nx ny nz f_dc_0..2 f_rest_0..f_rest_{3K-1} opacity
  scale_0..2 rot_0..3``. Normals are written as zeros (INRIA includes them;
  the viewer ignores them but third-party tools expect them).
- ``f_rest`` is channel-major: the ``(N, K, 3)`` higher-order SH tensor is
  transposed to ``(N, 3, K)`` before flattening — all R coefficients, then
  all G, then all B.
- ``rot_0..3`` is a quaternion in w, x, y, z order (gsplat's native order).
- ``opacity`` is a raw logit and ``scale_*`` are log-space values — the
  viewer applies sigmoid/exp itself.

This module uses only the stdlib and numpy; it must import without torch or
gsplat installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Accept both Unix (\n) and Windows (\r\n) line endings in the PLY header,
# mirroring _load_ply_positions_and_colors in reconstruction.py.
_HEADER_END_MARKERS = (b"\nend_header\r\n", b"\nend_header\n")

# Property count before f_rest_* (x y z nx ny nz f_dc_0..2) plus after
# (opacity scale_0..2 rot_0..3).
_NUM_FIXED_PROPERTIES = 17


@dataclass
class GaussianCloud:
    """One Gaussian-splat scene in gsplat's native parameterization.

    Attributes:
        means: (N, 3) float32 Gaussian centers.
        sh0: (N, 3) float32 DC spherical-harmonic coefficients (f_dc_0..2).
        shN: (N, K, 3) float32 higher-order SH coefficients; K may be 0.
        opacities: (N,) float32 raw logits (sigmoid is NOT applied).
        scales: (N, 3) float32 log-space scales (exp is NOT applied).
        quats: (N, 4) float32 rotation quaternions in w, x, y, z order.
    """

    means: np.ndarray
    sh0: np.ndarray
    shN: np.ndarray
    opacities: np.ndarray
    scales: np.ndarray
    quats: np.ndarray


def ply_property_names(sh_degree: int) -> list[str]:
    """Return vertex property names, in exact INRIA order, for an SH degree."""
    if sh_degree < 0:
        raise ValueError(f"sh_degree must be >= 0, got {sh_degree}")
    num_rest_coeffs = (sh_degree + 1) ** 2 - 1
    return _property_names_for_rest_coeffs(num_rest_coeffs)


def _property_names_for_rest_coeffs(num_rest_coeffs: int) -> list[str]:
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
    names += [f"f_rest_{i}" for i in range(3 * num_rest_coeffs)]
    names += ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    return names


def _validate_cloud(cloud: GaussianCloud) -> int:
    """Check attribute shapes are mutually consistent; return the row count N."""
    if cloud.means.ndim != 2 or cloud.means.shape[1] != 3:
        raise ValueError(f"GaussianCloud.means has shape {cloud.means.shape}, expected (N, 3)")
    n = cloud.means.shape[0]
    expected = {
        "sh0": (n, 3),
        "opacities": (n,),
        "scales": (n, 3),
        "quats": (n, 4),
    }
    for name, shape in expected.items():
        actual = getattr(cloud, name).shape
        if actual != shape:
            raise ValueError(f"GaussianCloud.{name} has shape {actual}, expected {shape}")
    if cloud.shN.ndim != 3 or cloud.shN.shape[0] != n or cloud.shN.shape[2] != 3:
        raise ValueError(f"GaussianCloud.shN has shape {cloud.shN.shape}, expected ({n}, K, 3)")
    return n


def write_3dgs_ply(path: Path, cloud: GaussianCloud) -> Path:
    """Write *cloud* to *path* as a binary little-endian INRIA 3DGS PLY."""
    n = _validate_cloud(cloud)
    num_rest_coeffs = cloud.shN.shape[1]
    names = _property_names_for_rest_coeffs(num_rest_coeffs)

    dtype = np.dtype([(name, "<f4") for name in names])
    rows = np.zeros(n, dtype=dtype)

    # Every field is "<f4", so the structured array can be filled through a
    # flat (N, P) float32 view; column order matches the property order.
    flat = rows.view("<f4").reshape(n, len(names))
    flat[:, 0:3] = cloud.means
    # Columns 3:6 are nx, ny, nz — left as zeros.
    flat[:, 6:9] = cloud.sh0
    # f_rest is channel-major: (N, K, 3) -> (N, 3, K) -> (N, 3K).
    flat[:, 9 : 9 + 3 * num_rest_coeffs] = cloud.shN.transpose(0, 2, 1).reshape(
        n, 3 * num_rest_coeffs
    )
    base = 9 + 3 * num_rest_coeffs
    flat[:, base] = cloud.opacities
    flat[:, base + 1 : base + 4] = cloud.scales
    flat[:, base + 4 : base + 8] = cloud.quats

    header_lines = ["ply", "format binary_little_endian 1.0", f"element vertex {n}"]
    header_lines += [f"property float {name}" for name in names]
    header_lines += ["end_header", ""]
    header = "\n".join(header_lines).encode("ascii")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + rows.tobytes())
    return path


def _split_header(data: bytes) -> tuple[str, bytes]:
    """Split raw PLY bytes into (header text, body bytes), tolerating \\r\\n."""
    for marker in _HEADER_END_MARKERS:
        index = data.find(marker)
        if index != -1:
            header_end = index + len(marker)
            return data[:header_end].decode("ascii", errors="replace"), data[header_end:]
    raise RuntimeError("PLY end_header marker not found")


def read_3dgs_ply(path: Path) -> GaussianCloud:
    """Read a binary little-endian INRIA 3DGS PLY into a :class:`GaussianCloud`."""
    header_text, body = _split_header(path.read_bytes())

    vertex_count = 0
    names: list[str] = []
    is_binary_little = False
    for line in header_text.splitlines():
        if line.startswith("format binary_little_endian"):
            is_binary_little = True
        elif line.startswith("element vertex"):
            vertex_count = int(line.split()[-1])
        elif line.startswith("property"):
            parts = line.split()
            if parts[1] != "float":
                raise RuntimeError(f"Unsupported 3DGS PLY property type: {parts[1]}")
            names.append(parts[2])

    if not is_binary_little:
        raise RuntimeError(f"3DGS PLY must be format binary_little_endian 1.0: {path}")

    rest_count = sum(1 for name in names if name.startswith("f_rest_"))
    if rest_count % 3 != 0:
        raise RuntimeError(f"f_rest property count {rest_count} is not a multiple of 3")
    num_rest_coeffs = rest_count // 3
    if names != _property_names_for_rest_coeffs(num_rest_coeffs):
        raise RuntimeError(f"PLY vertex properties do not match the INRIA 3DGS layout: {path}")

    dtype = np.dtype([(name, "<f4") for name in names])
    expected_size = vertex_count * dtype.itemsize
    if len(body) < expected_size:
        raise RuntimeError(f"PLY body truncated: expected {expected_size} bytes, got {len(body)}")
    vertices = np.frombuffer(body, dtype=dtype, count=vertex_count)

    # Inverse of the write path: view the structured rows as a flat (N, P)
    # float32 matrix and slice columns back out.
    flat = vertices.view("<f4").reshape(vertex_count, len(names))
    rest = flat[:, 9 : 9 + 3 * num_rest_coeffs]
    shn = np.ascontiguousarray(
        rest.reshape(vertex_count, 3, num_rest_coeffs).transpose(0, 2, 1), dtype=np.float32
    )
    base = 9 + 3 * num_rest_coeffs
    return GaussianCloud(
        means=flat[:, 0:3].astype(np.float32),
        sh0=flat[:, 6:9].astype(np.float32),
        shN=shn,
        opacities=flat[:, base].astype(np.float32),
        scales=flat[:, base + 1 : base + 4].astype(np.float32),
        quats=flat[:, base + 4 : base + 8].astype(np.float32),
    )


def prune_by_opacity(src: Path, dst: Path, keep_ratio: float) -> Path:
    """Write the top *keep_ratio* fraction of Gaussians (by opacity) to *dst*.

    Opacities are raw logits; sigmoid is monotonic, so sorting logits directly
    gives the same order as sorting activated opacities. At least one Gaussian
    is always kept.
    """
    cloud = read_3dgs_ply(src)
    n = cloud.means.shape[0]
    keep = max(1, int(n * keep_ratio))
    order = np.argsort(-cloud.opacities, kind="stable")[:keep]
    pruned = GaussianCloud(
        means=cloud.means[order],
        sh0=cloud.sh0[order],
        shN=cloud.shN[order],
        opacities=cloud.opacities[order],
        scales=cloud.scales[order],
        quats=cloud.quats[order],
    )
    return write_3dgs_ply(dst, pruned)
