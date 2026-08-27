from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.elevation_export import (
    MAX_RASTER_PIXELS,
    NODATA,
    export_elevation_geotiff,
)


def _require_raster_dependencies() -> None:
    pytest.importorskip("laspy")
    pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")


@pytest.fixture
def classified_las(tmp_path: Path) -> Path:
    _require_raster_dependencies()
    import laspy
    import numpy as np
    from pyproj import CRS

    path = tmp_path / "pointcloud.las"
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.array([500000.0, 5000000.0, 0.0])
    header.add_crs(CRS.from_epsg(32617))
    cloud = laspy.LasData(header)
    cloud.x = [500000.1, 500000.1, 500001.1]
    cloud.y = [5000001.1, 5000001.1, 5000000.1]
    cloud.z = [10.0, 12.0, 8.0]
    cloud.classification = [2, 2, 1]
    cloud.write(path)
    return path


def test_dsm_geotiff_has_maximum_values_crs_and_nodata(classified_las: Path, tmp_path: Path):
    _require_raster_dependencies()
    import rasterio

    result = export_elevation_geotiff(
        classified_las, tmp_path / "dsm.tif", product="dsm", resolution_m=1.0
    )

    with rasterio.open(result["path"]) as dataset:
        values = dataset.read(1)
        assert dataset.crs.to_epsg() == 32617
        assert dataset.nodata == NODATA
        assert values.tolist() == [[12.0, NODATA], [NODATA, 8.0]]


def test_dem_requires_ground_labels(classified_las: Path, tmp_path: Path):
    _require_raster_dependencies()
    import laspy

    cloud = laspy.read(classified_las)
    cloud.classification = [1, 1, 1]
    cloud.write(classified_las)

    with pytest.raises(ValueError, match="no ASPRS ground"):
        export_elevation_geotiff(
            classified_las, tmp_path / "dem.tif", product="dem", resolution_m=1.0
        )


def test_over_pixel_budget_raises_before_allocation(tmp_path: Path):
    _require_raster_dependencies()
    import laspy
    import numpy as np
    from pyproj import CRS

    path = tmp_path / "wide.las"
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    header.offsets = np.array([500000.0, 5000000.0, 0.0])
    header.add_crs(CRS.from_epsg(32617))
    cloud = laspy.LasData(header)
    # ~300 m span at 0.02 m resolution -> 15001 x 15001 ~= 225 MP, over the 100 MP cap.
    cloud.x = [500000.0, 500300.0]
    cloud.y = [5000000.0, 5000300.0]
    cloud.z = [10.0, 12.0]
    cloud.classification = [2, 2]
    cloud.write(path)

    with pytest.raises(ValueError, match=str(MAX_RASTER_PIXELS)):
        export_elevation_geotiff(path, tmp_path / "dsm.tif", product="dsm", resolution_m=0.02)
    # Guard fired before the raster was written: no output file allocated.
    assert not (tmp_path / "dsm.tif").exists()


@pytest.mark.parametrize("resolution_m", [1e-310, 0.001])
def test_below_resolution_floor_raises_before_reading_the_cloud(
    tmp_path: Path, resolution_m: float
):
    # No raster dependencies needed: the floor guard must fire before the optional imports and
    # before laspy.read. The path does not exist, so reaching the read raises a non-ValueError,
    # and 1e-310 would overflow math.floor to OverflowError once dimensions were computed.
    with pytest.raises(ValueError, match="at least"):
        export_elevation_geotiff(
            tmp_path / "missing.las", tmp_path / "dsm.tif", product="dsm", resolution_m=resolution_m
        )


def test_elevation_route_returns_422_below_resolution_floor(
    client, classified_las: Path, monkeypatch, tmp_path
):
    import backend.routers.export as export_router
    from backend.main import app

    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    exports = tmp_path / "exports" / "1"
    exports.mkdir(parents=True)
    pointcloud = exports / "pointcloud.las"
    pointcloud.write_bytes(classified_las.read_bytes())

    db = app.state.test_db_session
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    rec = Reconstruction(session_id=session.id, status="complete", pointcloud_path=str(pointcloud))
    db.add(rec)
    db.commit()
    db.refresh(rec)

    # Router accepts 0.001 (> 0); the service floor guards the OOM allocation.
    response = client.post(
        f"/export/reconstructions/{rec.id}/elevation?product=dsm&resolution_m=0.001"
    )

    assert response.status_code == 422
    assert "at least" in response.json()["detail"]


def test_dem_route_returns_422_without_ground_labels(
    client, classified_las: Path, monkeypatch, tmp_path
):
    import backend.routers.export as export_router
    from backend.main import app

    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    exports = tmp_path / "exports" / "1"
    exports.mkdir(parents=True)
    pointcloud = exports / "pointcloud.las"
    pointcloud.write_bytes(classified_las.read_bytes())
    import laspy

    cloud = laspy.read(pointcloud)
    cloud.classification = [1, 1, 1]
    cloud.write(pointcloud)

    db = app.state.test_db_session
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    rec = Reconstruction(session_id=session.id, status="complete", pointcloud_path=str(pointcloud))
    db.add(rec)
    db.commit()
    db.refresh(rec)

    response = client.post(
        f"/export/reconstructions/{rec.id}/elevation?product=dem&resolution_m=1"
    )

    assert response.status_code == 422
    assert "no ASPRS ground" in response.json()["detail"]
