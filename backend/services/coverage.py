from __future__ import annotations

import json

import pyproj
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union


def run_coverage(footprint_geojsons: list[str], target_geojson: str) -> dict:
    """Returns covered_area_m2, coverage_pct, gap_geojson, overlap_geojson.

    Computes area in a projected CRS (UTM auto-zone from the target centroid)
    so that area numbers are real m², not square degrees.
    """
    target = shape(json.loads(target_geojson))
    if not footprint_geojsons:
        return {
            "covered_area_m2": 0.0,
            "coverage_pct": 0.0,
            "gap_geojson": target_geojson,
            "overlap_geojson": None,
        }
    polys = [shape(json.loads(g)) for g in footprint_geojsons]

    # Determine UTM CRS from the target centroid
    centroid = target.centroid
    utm_zone = int((centroid.x + 180) / 6) + 1
    is_southern = centroid.y < 0.0
    utm_crs = pyproj.CRS.from_dict({"proj": "utm", "zone": utm_zone, "south": is_southern})
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True).transform
    to_wgs84 = pyproj.Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True).transform

    # Project all geometries to UTM for area computation
    target_utm = transform(to_utm, target)
    polys_utm = [transform(to_utm, p) for p in polys]

    union_utm = unary_union(polys_utm)
    covered_utm = union_utm.intersection(target_utm)
    gap = target.difference(union)

    # Compute pairwise overlap (double-coverage regions) in UTM
    from shapely.ops import unary_union as _unary
    import itertools
    overlap_polys = []
    for a, b in itertools.combinations(polys_utm, 2):
        inter = a.intersection(b)
        if not inter.is_empty:
            overlap_polys.append(inter)
    overlap_utm = _unary(overlap_polys) if overlap_polys else None
    overlap_wgs84 = transform(to_wgs84, overlap_utm) if overlap_utm else None

    covered_area_m2 = covered_utm.area
    pct = (covered_utm.area / target_utm.area * 100) if target_utm.area > 0 else 0.0

    # Project gap back to WGS84 for GeoJSON output
    gap_wgs84 = transform(to_wgs84, transform(to_utm, gap)) if not gap.is_empty else None

    return {
        "covered_area_m2": round(covered_area_m2, 2),
        "coverage_pct": round(pct, 2),
        "gap_geojson": json.dumps(mapping(gap_wgs84)) if gap_wgs84 else None,
        "overlap_geojson": json.dumps(mapping(overlap_wgs84)) if overlap_wgs84 else None,
    }
