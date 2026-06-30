from __future__ import annotations

import json
import zipfile
from pathlib import Path

from backend.db.models import Reconstruction

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


def build_share_bundle(zip_path: Path, rec: Reconstruction) -> dict:
    manifest = build_share_manifest(rec)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    copied = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        text = json.dumps(manifest, indent=2)
        zf.writestr("manifest.json", text)
        zf.writestr("index.html", VIEWER_HTML.replace("MANIFEST_JSON", text.replace("</", "<\\/")))
        zf.writestr(
            "tileset.json",
            json.dumps(
                {
                    "asset": {"version": "1.1"},
                    "geometricError": 0,
                    "root": {"boundingVolume": {"region": [0, 0, 0, 0, 0, 0]}, "geometricError": 0},
                },
                indent=2,
            ),
        )
        for label, raw in manifest["artifacts"].items():
            p = Path(raw)
            if p.is_file():
                zf.write(p, f"artifacts/{p.name}")
                copied.append({"label": label, "path": f"artifacts/{p.name}"})
    manifest["bundle_path"] = str(zip_path)
    manifest["bundled_artifacts"] = copied
    return manifest
