from __future__ import annotations

import json
import zipfile
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


def build_share_bundle(zip_path: Path, rec: Reconstruction, exports_dir: Path) -> dict:
    try:
        zip_path = confine_path(zip_path, exports_dir, allow_root=False)
    except ValueError as exc:
        raise ValueError(f"Share bundle path {zip_path} is outside exports directory") from exc

    manifest = build_share_manifest(rec)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    copied = []

    # The glb, if bundled, is where the tileset's root.content.uri must point —
    # figure out its bundle-relative path before writing the tileset.
    mesh_glb = Path(rec.mesh_glb_path) if rec.mesh_glb_path else None
    content_uri = f"artifacts/{mesh_glb.name}" if mesh_glb and mesh_glb.is_file() else None
    images = rec.session.images if rec.session else []
    tileset = build_tileset(images, content_uri)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        text = json.dumps(manifest, indent=2)
        zf.writestr("manifest.json", text)
        zf.writestr("index.html", VIEWER_HTML.replace("MANIFEST_JSON", text.replace("</", "<\\/")))
        zf.writestr("tileset.json", json.dumps(tileset, indent=2))
        for label, raw in manifest["artifacts"].items():
            p = Path(raw)
            if p.is_file():
                zf.write(p, f"artifacts/{p.name}")
                copied.append({"label": label, "path": f"artifacts/{p.name}"})
    manifest["bundle_path"] = str(zip_path)
    manifest["bundled_artifacts"] = copied
    return manifest
