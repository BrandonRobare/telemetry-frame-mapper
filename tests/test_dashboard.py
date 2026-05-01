from __future__ import annotations

import io
import json
import socket
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers to spin up the real _Handler on a random port
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _Server(threading.Thread):
    """Thin wrapper that starts the dashboard HTTP server in a background thread."""

    def __init__(self, port: int):
        super().__init__(daemon=True)
        import http.server
        from dashboard.server import _Handler
        self.server = http.server.HTTPServer(('127.0.0.1', port), _Handler)
        self.port = port

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


@pytest.fixture()
def server():
    port = _free_port()
    srv = _Server(port)
    srv.start()
    yield port
    srv.stop()


def _get(port: int, path: str):
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('GET', path)
    return conn.getresponse()


# ---------------------------------------------------------------------------
# parse_plan unit tests
# ---------------------------------------------------------------------------

from dashboard.server import parse_plan, _finalize


PLAN_SAMPLE = """\
## Task 1: Setup

**Files:** `src/main.py`

- [x] **Step 1: Init**
- [x] **Step 2: Config**
- [ ] **Step 3: Tests**

---

## Task 2: 🤖 Build routes

**Files:** `backend/routes.py`

- [x] **Step 1: Scaffold**
"""


def test_parse_plan_task_count():
    tasks = parse_plan(PLAN_SAMPLE)
    assert len(tasks) == 2


def test_parse_plan_status_in_progress():
    tasks = parse_plan(PLAN_SAMPLE)
    assert tasks[0]['status'] == 'in-progress'
    assert tasks[0]['progress'] == {'done': 2, 'total': 3}


def test_parse_plan_status_complete():
    tasks = parse_plan(PLAN_SAMPLE)
    assert tasks[1]['status'] == 'complete'
    assert tasks[1]['progress'] == {'done': 1, 'total': 1}


def test_parse_plan_codex_flag():
    tasks = parse_plan(PLAN_SAMPLE)
    assert tasks[0]['codex'] is False
    assert tasks[1]['codex'] is True


def test_parse_plan_files():
    tasks = parse_plan(PLAN_SAMPLE)
    assert 'src/main.py' in tasks[0]['files']
    assert 'backend/routes.py' in tasks[1]['files']


def test_parse_plan_no_duplicate_files():
    md = """\
## Task 1: Dup

**Files:** `foo.py`, `foo.py`

- [x] **Step 1**
"""
    tasks = parse_plan(md)
    assert tasks[0]['files'].count('foo.py') == 1


def test_parse_plan_empty():
    assert parse_plan('') == []


def test_parse_plan_pending_when_no_steps():
    md = "## Task 1: Empty\n\n**Files:** `x.py`\n"
    tasks = parse_plan(md)
    assert tasks[0]['status'] == 'pending'
    assert tasks[0]['progress'] == {'done': 0, 'total': 0}


# ---------------------------------------------------------------------------
# Static file serving — security (path traversal) and happy path
# ---------------------------------------------------------------------------

def test_styles_css_served(server, tmp_path, monkeypatch):
    """styles.css in the dashboard dir must be served with correct content-type."""
    import dashboard.server as ds
    css = (Path(ds.__file__).parent / 'styles.css')
    resp = _get(server, '/styles.css')
    if css.exists():
        assert resp.status == 200
        assert 'text/css' in resp.getheader('Content-Type', '')
    else:
        assert resp.status == 404


def test_unknown_file_returns_404(server):
    resp = _get(server, '/nonexistent.js')
    assert resp.status == 404


def test_path_traversal_blocked(server):
    """Attempts to escape the dashboard directory must return 404, not file contents."""
    for evil in (
        '/../../../etc/passwd',
        '/..%2F..%2Fetc%2Fpasswd',
        '/styles.css/../../../etc/passwd',
    ):
        resp = _get(server, evil)
        assert resp.status == 404, f"Expected 404 for {evil!r}, got {resp.status}"


def test_only_allowlisted_extensions_served(server):
    """Files with extensions not in the allowlist must 404 even if they exist."""
    resp = _get(server, '/server.py')
    assert resp.status == 404


def test_root_returns_html(server):
    resp = _get(server, '/')
    import dashboard.server as ds
    if ds.HTML_PATH.exists():
        assert resp.status == 200
        assert 'text/html' in resp.getheader('Content-Type', '')
    else:
        assert resp.status == 404


def test_api_status_returns_json(server, monkeypatch):
    """GET /api/status returns valid JSON even when the plan file is missing."""
    import dashboard.server as ds
    monkeypatch.setattr(ds, 'PLAN_PATH', Path('/nonexistent/plan.md'))
    resp = _get(server, '/api/status')
    assert resp.status == 200
    body = json.loads(resp.read())
    assert 'tasks' in body
    assert 'error' in body  # plan file missing → error key present
