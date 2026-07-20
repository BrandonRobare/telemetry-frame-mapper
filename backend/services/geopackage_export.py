from __future__ import annotations

import sqlite3
from pathlib import Path

LAYER_COLUMNS = {
    "image_locations": [
        "image_id",
        "filename",
        "timestamp",
        "altitude_m",
        "gps_source",
        "usable",
        "geometry",
    ],
    "footprints": [
        "footprint_id", "image_id", "filename", "ground_width_m", "ground_height_m",
        "heading_estimated", "pitch_oblique", "geometry",
    ],
    "flight_paths": ["flight_log_id", "filename", "point_count", "geometry"],
    "coverage_gaps": ["reconstruction_id", "level", "size_m", "geometry"],
    "measurements": [
        "measurement_id", "kind", "label", "value", "unit", "created_at", "geometry"
    ],
    "comparison_change_cells": ["comparison_id", "change_type", "size_m", "geometry"],
}


def write_geopackage(
    output_path: Path,
    layers: list[tuple[str, list[dict], str]],
    target_crs: str,
    raster_references: list[dict],
) -> None:
    """Write populated vector layers and optional DSM/DEM references to a GeoPackage."""
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise RuntimeError(
            "GeoPackage export requires geopandas; install the backend extra"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    wrote_layer = False
    for name, records, source_crs in layers:
        if not records:
            continue
        frame = gpd.GeoDataFrame(
            records,
            columns=LAYER_COLUMNS[name],
            geometry="geometry",
            crs=source_crs,
        ).to_crs(target_crs)
        frame.to_file(
            output_path,
            layer=name,
            driver="GPKG",
            index=False,
            mode="a" if wrote_layer else "w",
        )
        wrote_layer = True

    if not wrote_layer:
        raise ValueError("No exportable mapped geometry is available")
    if raster_references:
        _write_raster_references(output_path, raster_references)


def _write_raster_references(output_path: Path, references: list[dict]) -> None:
    """Add a non-spatial table; rasters remain external sidecar files."""
    connection = sqlite3.connect(output_path)
    try:
        connection.execute(
            "CREATE TABLE raster_references ("
            "product TEXT NOT NULL, path TEXT NOT NULL, embedded BOOLEAN NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO raster_references (product, path, embedded) VALUES (?, ?, 0)",
            [(reference["product"], reference["path"]) for reference in references],
        )
        connection.execute(
            "INSERT INTO gpkg_contents "
            "(table_name, data_type, identifier, description, last_change, srs_id) "
            "VALUES ('raster_references', 'attributes', 'raster_references', "
            "'External DSM/DEM sidecars; not embedded', "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), NULL)"
        )
        connection.commit()
    finally:
        connection.close()
