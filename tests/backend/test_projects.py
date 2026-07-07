from __future__ import annotations


def test_list_projects_empty(client):
    resp = client.get("/projects/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_project(client):
    resp = client.post("/projects/", json={"name": "Test Site", "description": "A test project"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Site"
    assert data["description"] == "A test project"
    assert data["session_count"] == 0
    assert "id" in data


def test_list_projects_after_create(client):
    client.post("/projects/", json={"name": "Site A"})
    client.post("/projects/", json={"name": "Site B"})
    resp = client.get("/projects/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert "Site A" in names
    assert "Site B" in names
    # Most recent first (Site B created after Site A).
    assert data[0]["name"] == "Site B"


def test_create_project_duplicate(client):
    client.post("/projects/", json={"name": "Dup"})
    resp = client.post("/projects/", json={"name": "Dup"})
    assert resp.status_code == 409


def test_get_project(client):
    create = client.post("/projects/", json={"name": "Single"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Single"


def test_get_project_not_found(client):
    resp = client.get("/projects/99999")
    assert resp.status_code == 404


def test_delete_project(client):
    create = client.post("/projects/", json={"name": "ToDelete"})
    pid = create.json()["id"]

    resp = client.delete(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 404


def test_project_session_count(client):
    """session_count field is computed, not a column."""
    create = client.post("/projects/", json={"name": "Counted"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["session_count"] == 0


def test_list_project_sessions_empty(client):
    create = client.post("/projects/", json={"name": "EmptySessions"})
    pid = create.json()["id"]

    resp = client.get(f"/projects/{pid}/sessions")
    assert resp.status_code == 200
    assert resp.json() == []