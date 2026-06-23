from __future__ import annotations

import json
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def parse_geojson_geometry(geom_geojson: str | None) -> dict | None:
    if not geom_geojson:
        return None
    try:
        geometry = json.loads(geom_geojson)
    except json.JSONDecodeError:
        return None
    if geometry.get("type") == "Feature":
        return geometry.get("geometry")
    return geometry


def geometry_feature(
    geometry: dict | None, name: str, properties: dict | None = None
) -> dict | None:
    if not geometry:
        return None
    props = dict(properties or {})
    props["name"] = name
    return {"type": "Feature", "geometry": geometry, "properties": props}


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _coord_text(coords: list) -> str:
    values: list[str] = []
    for coord in coords:
        if len(coord) < 2:
            continue
        lon = coord[0]
        lat = coord[1]
        alt = coord[2] if len(coord) > 2 else 0
        values.append(f"{lon},{lat},{alt}")
    return " ".join(values)


def _kml_geometry(geom: dict) -> str:
    geom_type = geom.get("type")
    coords = geom.get("coordinates")
    if geom_type == "Point":
        return f"<Point><coordinates>{_coord_text([coords or []])}</coordinates></Point>"
    if geom_type == "LineString":
        return f"<LineString><coordinates>{_coord_text(coords or [])}</coordinates></LineString>"
    if geom_type == "MultiLineString":
        parts = [
            _kml_geometry({"type": "LineString", "coordinates": line})
            for line in coords or []
        ]
        return f"<MultiGeometry>{''.join(parts)}</MultiGeometry>"
    if geom_type == "Polygon":
        rings = coords or []
        if not rings:
            return ""
        outer = _coord_text(rings[0])
        inners = "".join(
            "<innerBoundaryIs><LinearRing><coordinates>"
            f"{_coord_text(ring)}"
            "</coordinates></LinearRing></innerBoundaryIs>"
            for ring in rings[1:]
        )
        return (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{outer}"
            "</coordinates></LinearRing></outerBoundaryIs>"
            f"{inners}</Polygon>"
        )
    if geom_type == "MultiPolygon":
        parts = [
            _kml_geometry({"type": "Polygon", "coordinates": polygon})
            for polygon in coords or []
        ]
        return f"<MultiGeometry>{''.join(parts)}</MultiGeometry>"
    if geom_type == "GeometryCollection":
        parts = [_kml_geometry(child) for child in geom.get("geometries", [])]
        return f"<MultiGeometry>{''.join(parts)}</MultiGeometry>"
    return ""


def geojson_to_kml(collection: dict, document_name: str) -> bytes:
    placemarks: list[str] = []
    for index, feature in enumerate(collection.get("features", []), start=1):
        geometry = feature.get("geometry") or {}
        body = _kml_geometry(geometry)
        if not body:
            continue
        props = feature.get("properties") or {}
        name = escape(str(props.get("name") or props.get("id") or f"feature-{index}"))
        placemarks.append(f"<Placemark><name>{name}</name>{body}</Placemark>")
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        f"<Document><name>{escape(document_name)}</name>{''.join(placemarks)}</Document>"
        "</kml>"
    )
    return kml.encode("utf-8")


def kml_to_kmz(kml: bytes, filename: str = "doc.kml") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(filename, kml)
    return buffer.getvalue()
