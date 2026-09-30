from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path

from backend.core.config import get_config
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


def _artifact_sources(rec: Reconstruction) -> dict[str, str]:
    """Server-side path of each recorded artifact, keyed by its manifest label."""
    artifacts = {
        "pointcloud_las": rec.pointcloud_path,
        "mesh_glb": rec.mesh_glb_path,
        "mesh_obj": rec.mesh_obj_path,
        "splat_ply": rec.splat_path,
        "preview_splat_ply": rec.splat_preview_path,
        "medium_splat_ply": rec.splat_medium_path,
    }
    return {k: v for k, v in artifacts.items() if v}


def build_share_manifest(rec: Reconstruction) -> dict:
    """Bundle metadata. ``artifacts`` is filled with bundle-relative paths as files are
    bundled; server filesystem paths never enter a bundle that leaves this machine."""
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
        "artifacts": {},
    }


@contextmanager
def _bundle_parent(zip_path: Path, exports_dir: Path):
    """Anchor all destination operations to directory descriptors, not checked path strings."""
    if os.name == "nt":
        # Windows lacks Python's dir_fd/O_NOFOLLOW support. Recheck before creating
        # anything, and keep this platform's existing path-based atomic behavior.
        confine_path(zip_path, exports_dir, allow_root=False)
        Path(exports_dir).mkdir(parents=True, exist_ok=True)
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


@contextmanager
def _artifact_source(raw: str, exports_dir: Path, reconstruction_id: int | None):
    """Open a regular artifact below an app-owned root, never following child symlinks.

    Configured root ancestors are trusted; reconstruction metadata cannot add roots.
    Reject even in-root symlinks rather than attempting to resolve them during a race.
    """
    cfg = get_config()
    roots = [exports_dir, Path(cfg.processed_dir)]
    if reconstruction_id is not None and reconstruction_id > 0:
        roots.append(Path(cfg.data_dir) / "colmap" / str(reconstruction_id))
    path = Path(raw)
    if ".." in path.parts:
        raise ValueError("Artifact path outside authorized artifact roots")
    absolute = Path(os.path.abspath(path))
    selected = None
    for configured in roots:
        # The configured directory itself can be an intentional symlink.
        for prefix in (Path(os.path.abspath(configured)), Path(os.path.realpath(configured))):
            try:
                relative = absolute.relative_to(prefix)
            except ValueError:
                continue
            if relative.parts:
                selected = Path(os.path.realpath(configured)), relative.parts
                break
        if selected is not None:
            break
    if selected is None:
        raise ValueError("Artifact path outside authorized artifact roots")
    root, parts = selected
    if "\\" in parts[-1] or ":" in parts[-1] or any(ord(c) < 32 for c in parts[-1]):
        raise ValueError("Unsafe artifact name")
    if os.name == "nt":
        # Python on Windows lacks dir_fd/O_NOFOLLOW. This is a best-effort
        # recheck, not a defense against a local writer replacing a directory.
        source_path = confine_path(absolute, root)
        try:
            fd = os.open(source_path, os.O_RDONLY)
        except FileNotFoundError:
            yield None
            return
    else:
        try:
            parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            yield None
            return
        try:
            for component in parts[:-1]:
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=parent_fd,
                    )
                except FileNotFoundError:
                    yield None
                    return
                except OSError as exc:
                    raise ValueError("Cannot bundle symlink artifact parent") from exc
                os.close(parent_fd)
                parent_fd = child
            try:
                fd = os.open(
                    parts[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                yield None
                return
            except OSError as exc:
                raise ValueError("Cannot bundle symlink artifact") from exc
        finally:
            os.close(parent_fd)
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Cannot bundle non-file artifact")
        yield source


def build_share_bundle(zip_path: Path, rec: Reconstruction, exports_dir: Path) -> dict:
    try:
        zip_path = confine_path(zip_path, exports_dir, allow_root=False)
    except ValueError as exc:
        raise ValueError(f"Share bundle path {zip_path} is outside exports directory") from exc

    if "\\" in zip_path.name or ":" in zip_path.name or any(ord(c) < 32 for c in zip_path.name):
        raise ValueError("Unsafe share bundle name")
    manifest = build_share_manifest(rec)
    copied = []

    images = rec.session.images if rec.session else []

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
                    rec_id = rec.id if isinstance(rec.id, int) else None
                    for label, raw in _artifact_sources(rec).items():
                        p = Path(raw)
                        with _artifact_source(raw, exports_dir, rec_id) as source:
                            if source is None:
                                continue
                            arcname = f"artifacts/{p.name}"
                            with zf.open(arcname, "w") as target:
                                shutil.copyfileobj(source, target)
                            copied.append({"label": label, "path": arcname})
                    # Only what was bundled, by its path inside the bundle.
                    manifest["artifacts"] = {entry["label"]: entry["path"] for entry in copied}
                    text = json.dumps(manifest, indent=2)
                    zf.writestr("manifest.json", text)
                    zf.writestr(
                        "index.html",
                        VIEWER_HTML.replace("MANIFEST_JSON", text.replace("</", "<\\/")),
                    )
                    glb = next(
                        (entry["path"] for entry in copied if entry["label"] == "mesh_glb"), None
                    )
                    zf.writestr("tileset.json", json.dumps(build_tileset(images, glb), indent=2))
            os.replace(tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        finally:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
    manifest["bundle_path"] = str(zip_path)
    manifest["bundled_artifacts"] = copied
    return manifest
