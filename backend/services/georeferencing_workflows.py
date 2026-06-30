from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass

from backend.db.models import Image


@dataclass(frozen=True)
class GcpPoint:
    image_filename: str
    pixel_x: float
    pixel_y: float
    longitude: float
    latitude: float
    altitude_m: float | None = None
    label: str | None = None


def recommended_webodm_options(workflow: str, *, has_gcps: bool) -> list[str]:
    options = ["--use-exif"]
    if workflow in {"rtk", "ppk"}:
        options.append("--force-gps")
    if has_gcps:
        options.append("--gcp gcp_list.txt")
    return options


def detect_precision_workflow(images: Iterable[Image]) -> dict:
    images = list(images)
    sources = {str(image.gps_source or "none").lower() for image in images}
    usable_gps = [
        image
        for image in images
        if image.usable and image.latitude is not None and image.longitude is not None
    ]
    has_rtk = any("rtk" in source for source in sources)
    has_ppk = any("ppk" in source for source in sources)
    workflow = "rtk" if has_rtk else "ppk" if has_ppk else "exif"
    warnings: list[str] = []
    if not usable_gps:
        warnings.append("No usable GPS-tagged frames are available for georeferencing.")
    elif len(usable_gps) < 5:
        warnings.append("Fewer than five usable GPS frames; add GCPs before reconstruction.")
    if workflow == "exif":
        warnings.append("EXIF-only workflow detected; GCP/RTK/PPK control can improve accuracy.")
    return {
        "workflow": workflow,
        "gps_sources": sorted(sources),
        "total_images": len(images),
        "usable_gps_images": len(usable_gps),
        "rtk_detected": has_rtk,
        "ppk_detected": has_ppk,
        "recommended_webodm_options": recommended_webodm_options(workflow, has_gcps=False),
        "warnings": warnings,
    }


def render_gcp_list(points: Iterable[GcpPoint]) -> str:
    lines = ["# EPSG:4326"]
    for point in points:
        altitude = "" if point.altitude_m is None else f"{point.altitude_m:.3f}"
        label = point.label or point.image_filename
        lines.append(
            f"{point.longitude:.8f} {point.latitude:.8f} {altitude} "
            f"{point.pixel_x:.3f} {point.pixel_y:.3f} {point.image_filename} {label}".strip()
        )
    return "\n".join(lines) + "\n"


def parse_gcp_csv(text: str) -> list[GcpPoint]:
    reader = csv.DictReader(io.StringIO(text))
    required = {"image_filename", "pixel_x", "pixel_y", "longitude", "latitude"}
    if not reader.fieldnames or (missing := required - set(reader.fieldnames)):
        raise ValueError(f"Missing GCP columns: {sorted(missing)}")
    points: list[GcpPoint] = []
    for row in reader:
        points.append(
            GcpPoint(
                image_filename=row["image_filename"],
                pixel_x=float(row["pixel_x"]),
                pixel_y=float(row["pixel_y"]),
                longitude=float(row["longitude"]),
                latitude=float(row["latitude"]),
                altitude_m=float(row["altitude_m"]) if row.get("altitude_m") else None,
                label=row.get("label") or None,
            )
        )
    return points
