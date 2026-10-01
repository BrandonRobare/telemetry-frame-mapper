from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from backend.core.csv_safe import csv_safe
from backend.core.paths import confine_path
from backend.db.models import Image
from backend.services.georeferencing_workflows import render_gcp_list


@dataclass(frozen=True)
class WebodmPackageOptions:
    mode: str = "exif"
    include_images: bool = True
    include_gcp: bool = False


def package_image_names(images: Iterable[Image]) -> list[tuple[Image, str]]:
    """Pair each image with the one name it goes by in a WebODM package (#942).

    That name is both the image's ``odm_georeferencing.csv`` row and, under
    ``images/``, its zip member, so the two cannot drift apart. It is the stored
    filename, which ingest keeps unique when two folders ship the same camera name
    (the source path's basename does not), cut to a bare name so it can never become
    a path inside the zip. A name a spreadsheet would read as a formula gets a
    leading ``_``, so the CSV cell is inert without csv_safe's quote and still
    matches the member. Names still shared — merged sessions, or a case-only
    difference that collides on extraction — get a ``__N`` suffix.
    """
    named: list[tuple[Image, str]] = []
    taken: set[str] = set()
    for img in images:
        # PureWindowsPath strips "/", "\" and drive letters on any host OS.
        name = PureWindowsPath(img.filename or "").name
        if name in {"", ".."}:
            continue
        if csv_safe(name) != name:
            name = "_" + name
        stem, suffix = PurePosixPath(name).stem, PurePosixPath(name).suffix
        n = 1
        while name.casefold() in taken:
            n += 1
            name = f"{stem}__{n}{suffix}"
        taken.add(name.casefold())
        named.append((img, name))
    return named


def _number_cell(value: object) -> object:
    # Coordinates stay numeric, so a negative longitude gains no quote; anything else
    # is text and gets the formula guard. csv_safe(None) is "", and 0.0 stays 0.0.
    return value if isinstance(value, int | float) else csv_safe(value)


def odm_georeferencing_csv(named_images: Iterable[tuple[Image, str]]) -> str:
    """Render ``odm_georeferencing.csv`` from ``package_image_names`` pairs."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["filename", "latitude", "longitude", "altitude"])
    for img, name in named_images:
        writer.writerow(
            [
                csv_safe(name),
                _number_cell(img.latitude),
                _number_cell(img.longitude),
                _number_cell(img.altitude_m),
            ]
        )
    return output.getvalue()


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
    packaged = images
    if options.include_images:
        # List only images the zip will carry, so every CSV row has its member.
        packaged = [img for img in images if Path(img.filepath).is_file()]
    named = package_image_names(packaged)
    contents = []
    copied = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("odm_georeferencing.csv", odm_georeferencing_csv(named))
        contents.append("odm_georeferencing.csv")
        if options.include_images:
            for img, name in named:
                zf.write(img.filepath, f"images/{name}")
                contents.append(f"images/{name}")
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
        if options.include_gcp and not gcp_points:
            # The command above omits --gcp because the shipped file has no points.
            # Say so, or an operator who fills the template in gets it silently
            # ignored by ODM (#629).
            manifest["gcp_note"] = (
                "gcp_list.txt is an empty template. Add one row per control point "
                "(geo_x geo_y geo_z im_x im_y im_name gcp_label), then append "
                "'--gcp gcp_list.txt' to the command above. ODM ignores the file "
                "without that flag."
            )
        zf.writestr("odm_options_manifest.json", json.dumps(manifest, indent=2))
        contents.append("odm_options_manifest.json")
    manifest["contents"] = contents
    manifest["zip_path"] = str(zip_path)
    return manifest
