from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.db.models import Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.potree_export import _directory_prefix


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())


def _completed_reconstruction(client, pointcloud_path: Path | None = None):
    db = _db(client)
    session = SessionModel(name="S", folder_path=".")
    db.add(session)
    db.commit()
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        pointcloud_path=str(pointcloud_path) if pointcloud_path else None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def test_potree_export_requires_existing_las(client):
    rec = _completed_reconstruction(client)
    response = client.post(f"/reconstruction/{rec.id}/potree")
    assert response.status_code == 422
    assert "download the reconstruction point cloud first" in response.json()["detail"]


def test_potree_export_runs_converter_and_returns_metadata(client, tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    source = exports_dir / "1" / "pointcloud.las"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"LAS")
    monkeypatch.setattr(
        "backend.routers.reconstruction.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )
    monkeypatch.setattr(
        "backend.services.potree_export.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )

    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).joinpath("metadata.json").write_text("{}", encoding="utf-8")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(
        "backend.services.potree_export.shutil.which",
        lambda name: "converter" if name == "PotreeConverter" else None,
    )
    monkeypatch.setattr("backend.services.potree_export.subprocess.run", fake_run)
    rec = _completed_reconstruction(client, source)

    response = client.post(f"/reconstruction/{rec.id}/potree")

    assert response.status_code == 200
    assert Path(response.json()["metadata_path"]).is_file()
    assert calls == [["converter", str(source), "-o", str(exports_dir / str(rec.id) / "potree")]]


def test_potree_export_reports_missing_converter(client, tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    source = exports_dir / "1" / "pointcloud.las"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"LAS")
    monkeypatch.setattr(
        "backend.routers.reconstruction.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )
    monkeypatch.setattr(
        "backend.services.potree_export.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )
    monkeypatch.delenv("POTREE_CONVERTER", raising=False)
    monkeypatch.setattr("backend.services.potree_export.shutil.which", lambda _name: None)
    rec = _completed_reconstruction(client, source)

    response = client.post(f"/reconstruction/{rec.id}/potree")

    assert response.status_code == 422
    assert "POTREE_CONVERTER" in response.json()["detail"]


def test_potree_route_derives_output_from_persisted_id(tmp_path, monkeypatch):
    from backend.routers.reconstruction import generate_potree_export

    source = tmp_path / "pointcloud.las"
    source.write_bytes(b"LAS")
    rec = SimpleNamespace(id=7, pointcloud_path=str(source))
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = rec
    artifact_path = MagicMock(return_value=tmp_path)
    monkeypatch.setattr(
        "backend.routers.reconstruction._reconstruction_artifact_path",
        artifact_path,
    )
    monkeypatch.setattr(
        "backend.routers.reconstruction._safe_export_http_path", lambda path: path
    )
    monkeypatch.setattr(
        "backend.services.potree_export.export_potree",
        lambda _source, output: output / "metadata.json",
    )

    generate_potree_export(999, db)

    artifact_path.assert_called_once_with(rec.id, "potree")


def test_potree_export_rejects_paths_outside_exports(tmp_path, monkeypatch):
    exports_dir = tmp_path / "exports"
    source = exports_dir / "pointcloud.las"
    source.parent.mkdir()
    source.write_bytes(b"LAS")
    monkeypatch.setattr(
        "backend.services.potree_export.get_config",
        lambda: type("Cfg", (), {"exports_dir": str(exports_dir)})(),
    )

    from backend.services.potree_export import export_potree

    for output_dir in (
        exports_dir / ".." / "outside" / "potree",
        exports_dir.parent / "exports-other" / "potree",
    ):
        with pytest.raises(ValueError, match="inside the exports directory"):
            export_potree(source, output_dir)


def test_potree_path_check_preserves_filesystem_root():
    root = os.path.normcase(os.path.abspath(os.sep))

    assert _directory_prefix(root) == root
    assert os.path.normcase(os.path.join(root, "exports")).startswith(_directory_prefix(root))
