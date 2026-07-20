from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

_GPKG_NAME = "mapped_products.gpkg"
_QGIS_NAME = "mapped_products.qgz"
_ARCGIS_NAME = "mapped_products.lyrx"
_MANIFEST_NAME = "mapped_products_gis_manifest.json"


def write_gis_project_files(output_dir: Path) -> dict[str, list[str] | str]:
    """Write portable QGIS and ArcGIS Pro references for a sibling GeoPackage."""
    output_dir = output_dir.resolve()
    geopackage = output_dir / _GPKG_NAME
    if not geopackage.is_file():
        raise ValueError("Mapped-products GeoPackage was not created")

    layers = _geopackage_layers(geopackage)
    rasters = [name for name in ("dsm.tif", "dem.tif") if (output_dir / name).is_file()]
    qgis_path = output_dir / _QGIS_NAME
    arcgis_path = output_dir / _ARCGIS_NAME
    manifest_path = output_dir / _MANIFEST_NAME
    _write_qgis_project(qgis_path, layers, rasters)
    _write_arcgis_layer(arcgis_path, layers, rasters)
    manifest = {
        "files": [_GPKG_NAME, _QGIS_NAME, _ARCGIS_NAME, _MANIFEST_NAME],
        "layers": layers,
        "rasters": rasters,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _geopackage_layers(geopackage: Path) -> list[str]:
    connection = sqlite3.connect(geopackage)
    try:
        return [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features' ORDER BY rowid"
            )
        ]
    finally:
        connection.close()


def _write_qgis_project(path: Path, layers: list[str], rasters: list[str]) -> None:
    project = Element("qgis", version="3.34.0", projectname="Mapped products")
    tree = SubElement(
        project, "layer-tree-group", name="Mapped products", expanded="1", checked="Qt::Checked"
    )
    maplayers = SubElement(project, "maplayers")
    order = SubElement(project, "layerorder")
    for layer in layers:
        layer_id = f"mapped_products_{layer}"
        source = f"./{_GPKG_NAME}|layername={layer}"
        _add_qgis_layer(tree, maplayers, order, layer_id, layer, source, "vector", "ogr")
    for raster in rasters:
        layer_id = f"mapped_products_{raster.removesuffix('.tif')}"
        _add_qgis_layer(
            tree,
            maplayers,
            order,
            layer_id,
            raster.removesuffix(".tif"),
            f"./{raster}",
            "raster",
            "gdal",
        )

    project_xml = b"<?xml version='1.0' encoding='UTF-8'?>\n" + tostring(project, encoding="utf-8")
    info = zipfile.ZipInfo("mapped_products.qgs", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(info, project_xml)


def _add_qgis_layer(
    tree: Element,
    maplayers: Element,
    order: Element,
    layer_id: str,
    name: str,
    source: str,
    layer_type: str,
    provider: str,
) -> None:
    SubElement(
        tree,
        "layer-tree-layer",
        id=layer_id,
        name=name,
        source=source,
        providerKey=provider,
        expanded="1",
        checked="Qt::Checked",
    )
    layer = SubElement(maplayers, "maplayer", type=layer_type)
    SubElement(layer, "id").text = layer_id
    SubElement(layer, "datasource").text = source
    SubElement(layer, "layername").text = name
    SubElement(layer, "provider", encoding="UTF-8").text = provider
    SubElement(order, "layer", id=layer_id)


def _write_arcgis_layer(path: Path, layers: list[str], rasters: list[str]) -> None:
    definitions = [_arcgis_feature_layer(layer) for layer in layers]
    definitions.extend(_arcgis_raster_layer(raster) for raster in rasters)
    document = {
        "type": "CIMLayerDocument",
        "version": "3.0.0",
        "build": 0,
        "layers": [definition["uRI"] for definition in definitions],
        "layerDefinitions": definitions,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _arcgis_feature_layer(layer: str) -> dict:
    uri = f"CIMPATH=map/{layer}.xml"
    return {
        "type": "CIMFeatureLayer",
        "name": layer,
        "uRI": uri,
        "featureTable": {
            "type": "CIMFeatureTable",
            "dataConnection": {
                "type": "CIMStandardDataConnection",
                "workspaceConnectionString": f"DATABASE=./{_GPKG_NAME}",
                "workspaceFactory": "SQLite",
                "dataset": layer,
                "datasetType": "esriDTFeatureClass",
            },
        },
    }


def _arcgis_raster_layer(raster: str) -> dict:
    name = raster.removesuffix(".tif")
    return {
        "type": "CIMRasterLayer",
        "name": name,
        "uRI": f"CIMPATH=map/{name}.xml",
        "dataConnection": {
            "type": "CIMStandardDataConnection",
            "workspaceConnectionString": f"DATABASE=./{raster}",
            "workspaceFactory": "Raster",
            "dataset": raster,
            "datasetType": "esriDTRasterDataset",
        },
    }
