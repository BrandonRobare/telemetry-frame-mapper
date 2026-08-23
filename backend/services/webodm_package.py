from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from backend.core.paths import confine_path
from backend.db.models import Image
from backend.services.georeferencing_workflows import render_gcp_list


@dataclass(frozen=True)
class WebodmPackageOptions:
    mode: str = "exif"
    include_images: bool = True
    include_gcp: bool = False


def odm_georeferencing_csv(images: Iterable[Image]) -> str:
    rows = ["filename,latitude,longitude,altitude"]
    for img in images:
        lat = "" if img.latitude is None else img.latitude
        lon = "" if img.longitude is None else img.longitude
        alt = "" if img.altitude_m is None else img.altitude_m
        rows.append(f"{img.filename},{lat},{lon},{alt}")
    return "\n".join(rows) + "\n"


def odm_options_for(mode: str, *, has_gcp: bool) -> list[str]:
    if mode not in {"exif", "force_gps", "gcp"}:
        raise ValueError("mode must be one of: exif, force_gps, gcp")
    opts = ["--use-exif"]
    if mode == "force_gps":
        opts.append("--force-gps")
    # --gcp follows the file, not the mode label: advertising it for a
    # gcp_list.txt that holds no points makes ODM fail (#629).
    if has_gcp:
        opts.append("--gcp gcp_list.txt")
    return opts


def build_webodm_package(
    zip_path: Path, images: list[Image], options: WebodmPackageOptions, *, exports_dir: Path
) -> dict:
    try:
        zip_path = confine_path(zip_path, exports_dir, allow_root=False)
    except ValueError as exc:
        raise ValueError("Package path must be inside exports directory") from exc
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    contents = []
    copied = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("odm_georeferencing.csv", odm_georeferencing_csv(images))
        contents.append("odm_georeferencing.csv")
        if options.include_images:
            for img in images:
                src = Path(img.filepath)
                if src.is_file():
                    zf.write(src, f"images/{src.name}")
                    contents.append(f"images/{src.name}")
                    copied += 1
        # No surveyed GCPs are persisted anywhere yet, so include_gcp can only
        # ship a header-only template for the operator to fill in — and the
        # manifest must not tell them to pass --gcp for it (#629).
        # ponytail: pass real points here once GCPs are stored.
        gcp_points: list = []
        if options.include_gcp:
            zf.writestr("gcp_list.txt", render_gcp_list(gcp_points))
            contents.append("gcp_list.txt")
        odm_options = odm_options_for(options.mode, has_gcp=bool(gcp_points))
        manifest = {
            "export_type": "webodm_package",
            "mode": options.mode,
            "image_count": len(images),
            "copied_image_count": copied,
            "odm_options": odm_options,
            "copyable_command": "webodm run " + " ".join(odm_options),
            "contents": contents[:],
        }
        zf.writestr("odm_options_manifest.json", json.dumps(manifest, indent=2))
        contents.append("odm_options_manifest.json")
    manifest["contents"] = contents
    manifest["zip_path"] = str(zip_path)
    return manifest
