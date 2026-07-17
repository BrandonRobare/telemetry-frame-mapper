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


@dataclass(frozen=True)
class ControlPoint:
    """A surveyed WGS84 control point, independent of its image observations."""

    label: str
    latitude: float
    longitude: float
    altitude_m: float


_CONTROL_POINT_FORMATS = {"dronedeploy", "pix4d"}


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


def render_control_point_csv(points: Iterable[ControlPoint], format: str) -> str:
    """Render the common no-header WGS84 CSV accepted by Pix4D and DroneDeploy."""
    _validate_control_point_format(format)
    rows = []
    for point in points:
        _validate_control_point(point, "point")
        rows.append(
            [
                point.label,
                f"{point.latitude:.8f}",
                f"{point.longitude:.8f}",
                f"{point.altitude_m:.3f}",
            ]
        )
    if not rows:
        raise ValueError("At least one control point is required")
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue()


def parse_control_point_csv(text: str, format: str) -> list[ControlPoint]:
    """Parse the no-header ``label,latitude,longitude,elevation`` WGS84 contract.

    Pix4D's geographic GCP import and DroneDeploy's WGS84 import share this
    four-column shape. Projected CRS and Pix4D accuracy columns are left to
    those applications because this API intentionally stores WGS84 points only.
    """
    _validate_control_point_format(format)
    if not text.strip():
        raise ValueError("Control-point CSV is empty")
    reader = csv.reader(io.StringIO(text, newline=""))
    points: list[ControlPoint] = []
    labels: set[str] = set()
    for line_number, row in enumerate(reader, start=1):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) != 4:
            raise ValueError(
                f"Line {line_number}: expected 4 columns "
                "(label, latitude, longitude, elevation)"
            )
        label, latitude, longitude, altitude = (cell.strip() for cell in row)
        if not label:
            raise ValueError(f"Line {line_number}: label is required")
        if label in labels:
            raise ValueError(f"Line {line_number}: duplicate label '{label}'")
        try:
            point = ControlPoint(label, float(latitude), float(longitude), float(altitude))
        except ValueError as exc:
            raise ValueError(
                f"Line {line_number}: latitude, longitude, and elevation must be numbers"
            ) from exc
        _validate_control_point(point, f"Line {line_number}")
        labels.add(label)
        points.append(point)
    if not points:
        raise ValueError("Control-point CSV contains no data rows")
    return points


def _validate_control_point_format(format: str) -> None:
    if format not in _CONTROL_POINT_FORMATS:
        supported = ", ".join(sorted(_CONTROL_POINT_FORMATS))
        raise ValueError(f"format must be one of: {supported}")


def _validate_control_point(point: ControlPoint, location: str) -> None:
    if not point.label.strip():
        raise ValueError(f"{location}: label is required")
    if not -90 <= point.latitude <= 90:
        raise ValueError(f"{location}: latitude must be between -90 and 90")
    if not -180 <= point.longitude <= 180:
        raise ValueError(f"{location}: longitude must be between -180 and 180")
