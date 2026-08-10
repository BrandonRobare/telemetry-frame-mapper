from __future__ import annotations

import numpy as np
import pytest

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel


def _db():
    from backend.main import app

    return app.state.test_db_session


def _orthomosaic(tmp_path):
    pytest.importorskip("rasterio")
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "exports" / "1" / "orthomosaic.tif"
    path.parent.mkdir(parents=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=3,
        dtype="uint8",
        crs="EPSG:3857",
        transform=from_origin(0, 256, 128, 128),
    ) as dst:
        dst.write(np.full((3, 2, 2), 127, dtype=np.uint8))
    return path


def _rec(tmp_path, monkeypatch):
    from backend.core.config import get_config

    path = _orthomosaic(tmp_path)
    monkeypatch.setattr(get_config(), "exports_dir", str(tmp_path / "exports"))
    db = _db()
    session = SessionModel(name="Tiles", folder_path=str(tmp_path))
    db.add(session)
    db.commit()
    rec = Reconstruction(
        session_id=session.id, status="complete", ortho_status="complete", ortho_path=str(path)
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_wms_capabilities_and_getmap(client, tmp_path, monkeypatch):
    rec = _rec(tmp_path, monkeypatch)
    capabilities = client.get(f"/tiles/{rec.id}/wms?SERVICE=WMS&REQUEST=GetCapabilities")
    assert capabilities.status_code == 200
    assert f"reconstruction-{rec.id}" in capabilities.text
    image = client.get(
        f"/tiles/{rec.id}/wms",
        params={
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "LAYERS": f"reconstruction-{rec.id}",
            "CRS": "EPSG:3857",
            "BBOX": "0,0,256,256",
            "WIDTH": 2,
            "HEIGHT": 2,
            "FORMAT": "image/png",
        },
    )
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")
    tile = client.get(f"/tiles/{rec.id}/wmts/0/0/0.png")
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"


def test_wmts_validation_and_missing_orthomosaic(client, tmp_path, monkeypatch):
    rec = _rec(tmp_path, monkeypatch)
    assert client.get(f"/tiles/{rec.id}/wmts/1/2/0.png").status_code == 400
    assert (
        client.get(
            f"/tiles/{rec.id}/wms",
            params={
                "SERVICE": "WMS",
                "REQUEST": "GetMap",
                "LAYERS": "wrong",
                "CRS": "EPSG:3857",
                "BBOX": "0,0,1,1",
                "WIDTH": 1,
                "HEIGHT": 1,
            },
        ).status_code
        == 400
    )
    db = _db()
    pending = Reconstruction(session_id=rec.session_id, status="complete", ortho_status="pending")
    db.add(pending)
    db.commit()
    assert client.get(f"/tiles/{pending.id}/wms").status_code == 409
