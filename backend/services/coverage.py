from __future__ import annotations
import json
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


def run_coverage(footprint_geojsons: list[str], target_geojson: str) -> dict:
    """Returns covered_area_m2, coverage_pct, gap_geojson, overlap_geojson."""
    target = shape(json.loads(target_geojson))
    if not footprint_geojsons:
        return {
            "covered_area_m2": 0.0,
            "coverage_pct": 0.0,
            "gap_geojson": target_geojson,
            "overlap_geojson": None,
        }
    polys = [shape(json.loads(g)) for g in footprint_geojsons]
    union = unary_union(polys)
    covered = union.intersection(target)
    gap = target.difference(union)
    pct = (covered.area / target.area * 100) if target.area > 0 else 0.0
    return {
        "covered_area_m2": covered.area,
        "coverage_pct": round(pct, 2),
        "gap_geojson": json.dumps(mapping(gap)) if not gap.is_empty else None,
        "overlap_geojson": None,
    }
