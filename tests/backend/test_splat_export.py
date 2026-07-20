from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.ply_io import GaussianCloud, write_3dgs_ply


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def _make_rec(db, session, *, splat_path=None):
    rec = Reconstruction(
        session_id=session.id, status="complete", frames_used=5, splat_path=splat_path
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _write_splat_ply(path: Path, n: int) -> None:
    rng = np.random.default_rng(5)
    cloud = GaussianCloud(
        means=rng.normal(size=(n, 3)).astype(np.float32),
        sh0=rng.normal(size=(n, 3)).astype(np.float32),
        shN=rng.normal(size=(n, 3, 3)).astype(np.float32),
        opacities=rng.normal(size=(n,)).astype(np.float32),
        scales=rng.normal(size=(n, 3)).astype(np.float32),
        quats=rng.normal(size=(n, 4)).astype(np.float32),
    )
    write_3dgs_ply(path, cloud)


class TestCompactSplatExportRoute:
    def test_404_for_missing_reconstruction(self, client):
        resp = client.post("/export/reconstructions/9999/splat")
        assert resp.status_code == 404

    def test_422_when_reconstruction_has_no_splat(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = _make_rec(db, session, splat_path=None)
        resp = client.post(f"/export/reconstructions/{rec.id}/splat")
        assert resp.status_code == 422

    def test_happy_path_writes_compact_splat_and_reports_size(self, client, tmp_path, monkeypatch):
        exports_dir = tmp_path / "exports"
        monkeypatch.setattr(
            "backend.routers.export.get_config",
            lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
        )

        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat_path = tmp_path / "splat.ply"
        _write_splat_ply(splat_path, 20)
        rec = _make_rec(db, session, splat_path=str(splat_path))

        resp = client.post(f"/export/reconstructions/{rec.id}/splat")
        assert resp.status_code == 200
        body = resp.json()
        assert body["point_count"] == 20
        assert body["preset"] == "web"
        out = Path(body["splat_path"])
        assert out.parent == exports_dir.resolve()
        assert out.name == f"reconstruction_{rec.id}_web.splat"
        assert out.is_file()
        assert out.stat().st_size == 32 * 20
        assert body["byte_size"] == 32 * 20

    def test_preview_preset_prunes_point_count(self, client, tmp_path, monkeypatch):
        exports_dir = tmp_path / "exports"
        monkeypatch.setattr(
            "backend.routers.export.get_config",
            lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
        )

        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat_path = tmp_path / "splat.ply"
        _write_splat_ply(splat_path, 20)
        rec = _make_rec(db, session, splat_path=str(splat_path))

        resp = client.post(f"/export/reconstructions/{rec.id}/splat", params={"preset": "preview"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["point_count"] == 2  # 10% of 20
        assert body["byte_size"] == 32 * 2

    def test_unknown_preset_is_422(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)

        splat_path = tmp_path / "splat.ply"
        _write_splat_ply(splat_path, 5)
        rec = _make_rec(db, session, splat_path=str(splat_path))

        resp = client.post(f"/export/reconstructions/{rec.id}/splat", params={"preset": "bogus"})
        assert resp.status_code == 422

    def test_traversal_preset_is_rejected(self, client, tmp_path):
        db = _db(client)
        session = SessionModel(name="S", folder_path=str(tmp_path))
        db.add(session)
        db.commit()
        db.refresh(session)
        splat_path = tmp_path / "splat.ply"
        _write_splat_ply(splat_path, 5)
        rec = _make_rec(db, session, splat_path=str(splat_path))

        resp = client.post(
            f"/export/reconstructions/{rec.id}/splat", params={"preset": "../escape"}
        )

        assert resp.status_code == 422
