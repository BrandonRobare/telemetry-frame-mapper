from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path

from backend.core.paths import confine_path
from backend.db.models import Reconstruction
from backend.services.cesium_tiles import build_tileset

VIEWER_HTML = """
<!doctype html><meta charset='utf-8'>
<title>Telemetry Frame Mapper Share</title>
<div id='app'></div>
<script type='application/json' id='manifest'>MANIFEST_JSON</script>
<h1>Shareable reconstruction bundle</h1>
<p>Open manifest.json for artifact metadata. Cesium/3D Tiles handoff is described there.</p>
"""


def build_share_manifest(rec: Reconstruction) -> dict:
    artifacts = {
        "pointcloud_las": rec.pointcloud_path,
        "mesh_glb": rec.mesh_glb_path,
        "mesh_obj": rec.mesh_obj_path,
        "splat_ply": rec.splat_path,
        "preview_splat_ply": rec.splat_preview_path,
        "medium_splat_ply": rec.splat_medium_path,
    }
    return {
        "export_type": "shareable_reconstruction_bundle",
        "reconstruction_id": rec.id,
        "session_id": rec.session_id,
        "status": rec.status,
        "cesium": {
            "tileset_json": "tileset.json",
            "note": (
                "Full 3D Tiles conversion requires an external tiler; "
                "source artifacts are bundled when present."
            ),
        },
        "artifacts": {k: v for k, v in artifacts.items() if v},
    }


@contextmanager
def _bundle_parent(zip_path: Path, exports_dir: Path):
    """Anchor all destination operations to directory descriptors, not checked path strings."""
    if os.name == "nt":
        # Windows lacks Python's dir_fd/O_NOFOLLOW support. Recheck before creating
        # anything, and keep this platform's existing path-based atomic behavior.
        confine_path(zip_path, exports_dir, allow_root=False)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        confine_path(zip_path, exports_dir, allow_root=False)
        yield None, str(zip_path)
        return
    root = Path(os.path.realpath(exports_dir))
    relative = zip_path.relative_to(root)
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            # Do not create caller-named directories during bundle generation.
            # The HTTP route writes directly into exports_dir; nested callers
            # must provide an existing, non-symlinked directory.
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, relative.name
    finally:
        os.close(fd)


def build_share_bundle(zip_path: Path, rec: Reconstruction, exports_dir: Path) -> dict:
    try:
        zip_path = confine_path(zip_path, exports_dir, allow_root=False)
    except ValueError as exc:
        raise ValueError(f"Share bundle path {zip_path} is outside exports directory") from exc

    if "\\" in zip_path.name or ":" in zip_path.name or any(ord(c) < 32 for c in zip_path.name):
        raise ValueError("Unsafe share bundle name")
    manifest = build_share_manifest(rec)
    copied = []

    # The glb, if bundled, is where the tileset's root.content.uri must point —
    # figure out its bundle-relative path before writing the tileset.
    mesh_glb = Path(rec.mesh_glb_path) if rec.mesh_glb_path else None
    content_uri = f"artifacts/{mesh_glb.name}" if mesh_glb and mesh_glb.is_file() else None
    images = rec.session.images if rec.session else []
    tileset = build_tileset(images, content_uri)

    # Build into a unique sibling temp file inside the confined directory, then
    # os.replace onto the durable path: a concurrent writer or a crash mid-write
    # can never leave a half-written bundle at zip_path (#641).
    with _bundle_parent(zip_path, exports_dir) as (parent_fd, name):
        tmp_name = f"{name}.{secrets.token_hex(16)}.tmp"
        tmp_fd = os.open(
            tmp_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        try:
            with os.fdopen(tmp_fd, "w+b") as output:
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    text = json.dumps(manifest, indent=2)
                    zf.writestr("manifest.json", text)
                    zf.writestr(
                        "index.html",
                        VIEWER_HTML.replace("MANIFEST_JSON", text.replace("</", "<\\/")),
                    )
                    zf.writestr("tileset.json", json.dumps(tileset, indent=2))
                    for label, raw in manifest["artifacts"].items():
                        p = Path(raw)
                        if "\\" in p.name or ":" in p.name or any(ord(c) < 32 for c in p.name):
                            raise ValueError("Unsafe artifact name")
                        if p.is_symlink():
                            raise ValueError("Cannot bundle symlink artifact")
                        try:
                            source_fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                        except FileNotFoundError:
                            continue
                        except OSError as exc:
                            if p.is_symlink():
                                raise ValueError("Cannot bundle symlink artifact") from exc
                            raise
                        with os.fdopen(source_fd, "rb") as source:
                            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                                raise ValueError("Cannot bundle non-file artifact")
                            arcname = f"artifacts/{p.name}"
                            with zf.open(arcname, "w") as target:
                                shutil.copyfileobj(source, target)
                            copied.append({"label": label, "path": arcname})
            os.replace(tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        finally:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
    manifest["bundle_path"] = str(zip_path)
    manifest["bundled_artifacts"] = copied
    return manifest
