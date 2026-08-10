from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.slope_overlay import build_slope_overlay


def _require_rasterio() -> None:
    pytest.importorskip("rasterio")
    pytest.importorskip("pyproj")


def _write_dsm(path: Path, values) -> None:
    _require_rasterio()
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=len(values),
        width=len(values[0]),
        count=1,
        dtype="float32",
        crs="EPSG:32617",
        transform=from_origin(500000, 5000000, 1, 1),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.asarray(values, dtype=np.float32), 1)


def test_slope_overlay_writes_cached_png_with_transparent_no_data(tmp_path: Path):
    _require_rasterio()
    import rasterio

    dsm = tmp_path / "dsm.tif"
    overlay = tmp_path / "slope.png"
    _write_dsm(dsm, [[10, 11, 12], [10, 11, 12], [-9999, 11, 12]])

    result = build_slope_overlay(dsm, overlay)

    assert result["cached"] is False
    assert result["bounds"][0][0] < result["bounds"][1][0]
    with rasterio.open(overlay) as dataset:
        rgba = dataset.read()
    assert rgba.shape == (4, 3, 3)
    assert rgba[3, 2, 0] == 0
    assert rgba[3, 0, 1] == 255
    assert build_slope_overlay(dsm, overlay)["cached"] is True


def test_slope_route_returns_png_bounds_and_422_when_dsm_is_missing(client, monkeypatch, tmp_path):
    _require_rasterio()
    import backend.routers.export as export_router
    from backend.main import app

    monkeypatch.setattr(
        export_router,
        "get_config",
        lambda: type("Cfg", (), {"exports_dir": str(tmp_path / "exports")})(),
    )
    db = app.state.test_db_session
    session = SessionModel(name="S", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    rec = Reconstruction(session_id=session.id, status="complete")
    db.add(rec)
    db.commit()
    db.refresh(rec)

    missing = client.get(f"/export/reconstructions/{rec.id}/slope")
    assert missing.status_code == 422
    assert "DSM is unavailable" in missing.json()["detail"]

    dsm_dir = tmp_path / "exports" / str(rec.id)
    dsm_dir.mkdir(parents=True)
    _write_dsm(dsm_dir / "dsm.tif", [[10, 11], [10, 11]])
    response = client.get(f"/export/reconstructions/{rec.id}/slope")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    bounds = json.loads(response.headers["x-slope-bounds"])
    assert bounds[0][0] < bounds[1][0]
