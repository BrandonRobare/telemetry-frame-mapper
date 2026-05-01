from __future__ import annotations
import pytest
from backend.db.models import Session as SessionModel


def _make_session(client, name="Test Session"):
    from backend.db.database import get_db
    from backend.main import app
    db = next(app.dependency_overrides[get_db]())
    s = SessionModel(name=name, folder_path="/tmp/test", photo_count=0, usable_count=0)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_list_sessions_empty(client):
    resp = client.get("/sessions/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_session_not_found(client):
    resp = client.get("/sessions/999999")
    assert resp.status_code == 404


def test_get_session_found(client):
    s = _make_session(client)
    resp = client.get(f"/sessions/{s.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == s.id
    assert data["name"] == s.name


def test_delete_session(client):
    s = _make_session(client, name="ToDelete")
    resp = client.delete(f"/sessions/{s.id}")
    assert resp.status_code == 200
    assert client.get(f"/sessions/{s.id}").status_code == 404


def test_delete_session_not_found(client):
    resp = client.delete("/sessions/999999")
    assert resp.status_code == 404
