from __future__ import annotations
import json
import math
from pathlib import Path

from shapely.geometry import mapping, shape


def generate_lawnmower(
    target_geojson: str,
    altitude_ft: float,
    side_overlap: float,
    forward_overlap: float,
    fov_h_deg: float = 84.0,
    fov_v_deg: float = 64.0,
) -> dict:
    """Returns lanes_geojson, lane_count, total_distance_m."""
    poly = shape(json.loads(target_geojson))
    bounds = poly.bounds  # minx, miny, maxx, maxy

    altitude_m = altitude_ft * 0.3048
    gw = 2 * altitude_m * math.tan(math.radians(fov_h_deg / 2))
    lane_spacing = gw * (1 - side_overlap)
    if lane_spacing <= 0:
        lane_spacing = gw * 0.3  # fallback for degenerate overlap values

    # Convert lane_spacing from meters to degrees (approximate, using 111_000 m/deg)
    lane_spacing_deg = lane_spacing / 111_000

    minx, miny, maxx, maxy = bounds
    lanes = []
    x = minx + lane_spacing_deg / 2
    direction = 1
    while x <= maxx:
        if direction == 1:
            lanes.append([[x, miny], [x, maxy]])
        else:
            lanes.append([[x, maxy], [x, miny]])
        x += lane_spacing_deg
        direction *= -1

    total_dist = sum(math.dist(ln[0], ln[1]) * 111_000 for ln in lanes)

    return {
        "lanes_geojson": json.dumps({
            "type": "GeometryCollection",
            "geometries": [{"type": "LineString", "coordinates": ln} for ln in lanes],
        }),
        "lane_count": len(lanes),
        "total_distance_m": round(total_dist, 1),
    }


def write_kml(plan_id: int, lanes_geojson: str, exports_dir: Path) -> Path:
    """Write KML file for the given plan. Returns the file path."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    kml_path = exports_dir / f"plan_{plan_id}.kml"
    geo = json.loads(lanes_geojson)
    placemarks = ""
    for geom in geo.get("geometries", []):
        coords = " ".join(f"{c[0]},{c[1]},0" for c in geom["coordinates"])
        placemarks += f"<Placemark><LineString><coordinates>{coords}</coordinates></LineString></Placemark>\n"
    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>{placemarks}</Document>
</kml>"""
    kml_path.write_text(kml_content)
    return kml_path


def write_gpx(plan_id: int, lanes_geojson: str, exports_dir: Path) -> Path:
    """Write GPX file for the given plan. Returns the file path."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    gpx_path = exports_dir / f"plan_{plan_id}.gpx"
    geo = json.loads(lanes_geojson)
    trkseg_points = ""
    for geom in geo.get("geometries", []):
        for c in geom["coordinates"]:
            trkseg_points += f'<trkpt lat="{c[1]}" lon="{c[0]}"></trkpt>\n'
    gpx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg>{trkseg_points}</trkseg></trk>
</gpx>"""
    gpx_path.write_text(gpx_content)
    return gpx_path
