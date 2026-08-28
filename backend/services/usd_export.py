"""Small, dependency-free USDA geometry export from an existing OBJ mesh."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *path* via a unique sibling temp file, then ``os.replace`` it into place.

    A concurrent writer or a crash mid-write leaves the previous file intact (#641).
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _parse_obj_mesh(path: Path) -> tuple[list[tuple[float, float, float]], list[list[int]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "v" and len(parts) >= 4:
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError as exc:
                raise ValueError("OBJ contains an invalid vertex") from exc
        elif parts[0] == "f" and len(parts) >= 4:
            face: list[int] = []
            for item in parts[1:]:
                try:
                    index = int(item.split("/", 1)[0])
                except ValueError as exc:
                    raise ValueError("OBJ contains an invalid face index") from exc
                index = index - 1 if index > 0 else len(vertices) + index
                if index < 0 or index >= len(vertices):
                    raise ValueError("OBJ face index is outside its vertex list")
                face.append(index)
            faces.append(face)
    if not vertices or not faces:
        raise ValueError("OBJ must contain vertices and faces for USD export")
    return vertices, faces


def write_usda_handoff(
    output_dir: Path,
    source_obj: Path,
    *,
    reconstruction_id: int,
    session_id: int,
    geo_transform: dict,
    source_glb: Path | None = None,
) -> tuple[Path, Path]:
    """Write a valid USDA mesh and georeferencing sidecar from an existing OBJ."""
    vertices, faces = _parse_obj_mesh(source_obj)
    output_dir.mkdir(parents=True, exist_ok=True)
    usda_path = output_dir / "mesh.usda"
    sidecar_path = output_dir / "mesh.usd.georef.json"
    source_assets = {"obj": os.path.relpath(source_obj, output_dir).replace("\\", "/")}
    if source_glb is not None:
        source_assets["glb"] = os.path.relpath(source_glb, output_dir).replace("\\", "/")
    metadata = {
        "reconstruction_id": reconstruction_id,
        "session_id": session_id,
        "created_at": datetime.now(UTC).isoformat(),
        "source_assets": source_assets,
        "geo_transform": geo_transform,
        "transform_direction": (
            "USDA mesh XYZ -> UTM easting/northing/height: "
            "scale * (XYZ @ rotation.T) + translation + [utm_origin[0], utm_origin[1], 0]"
        ),
        "accuracy": (
            "The stored reconstruction transform is preserved without an accuracy claim. "
            "Use surveyed GCP/checkpoint results to establish accuracy."
        ),
    }
    _atomic_write_text(sidecar_path, json.dumps(metadata, indent=2, sort_keys=True))
    points = ", ".join(f"({x}, {y}, {z})" for x, y, z in vertices)
    counts = ", ".join(str(len(face)) for face in faces)
    indices = ", ".join(str(index) for face in faces for index in face)
    _atomic_write_text(
        usda_path,
        "#usda 1.0\n"
        "(\n"
        "    defaultPrim = \"ReconstructionMesh\"\n"
        "    metersPerUnit = 1\n"
        "    upAxis = \"Z\"\n"
        "    customLayerData = {\n"
        f"        string georeferencing_sidecar = {json.dumps(sidecar_path.name)}\n"
        "    }\n"
        ")\n\n"
        "def Mesh \"ReconstructionMesh\" (\n"
        "    customData = {\n"
        "        string source_format = \"OBJ mesh converted to USDA geometry\"\n"
        "        string georeferencing = \"See georeferencing_sidecar.\"\n"
        "    }\n"
        ")\n"
        "{\n"
        f"    int[] faceVertexCounts = [{counts}]\n"
        f"    int[] faceVertexIndices = [{indices}]\n"
        f"    point3f[] points = [{points}]\n"
        "}\n",
    )
    return usda_path, sidecar_path
