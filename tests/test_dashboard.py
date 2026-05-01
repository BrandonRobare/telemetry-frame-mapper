from __future__ import annotations

import json
import socket
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from dashboard.server import parse_plan


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class _Server(threading.Thread):
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
    assert len(parse_plan(PLAN_SAMPLE)) == 2


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
    md = "## Task 1: Dup\n\n**Files:** `foo.py`, `foo.py`\n\n- [x] **Step 1**\n"
    tasks = parse_plan(md)
    assert tasks[0]['files'].count('foo.py') == 1


def test_parse_plan_empty():
    assert parse_plan('') == []


def test_parse_plan_pending_when_no_steps():
    tasks = parse_plan("## Task 1: Empty\n\n**Files:** `x.py`\n")
    assert tasks[0]['status'] == 'pending'
    assert tasks[0]['progress'] == {'done': 0, 'total': 0}


def test_styles_css_served(server):
    import dashboard.server as ds
    resp = _get(server, '/styles.css')
    if (Path(ds.__file__).parent / 'styles.css').exists():
        assert resp.status == 200
        assert 'text/css' in resp.getheader('Content-Type', '')
    else:
        assert resp.status == 404


def test_unknown_file_returns_404(server):
    assert _get(server, '/nonexistent.js').status == 404


def test_path_traversal_blocked(server):
    for path in ('/../../../etc/passwd', '/..%2F..%2Fetc%2Fpasswd', '/styles.css/../../../etc/passwd'):
        assert _get(server, path).status == 404


def test_non_allowlisted_file_blocked(server):
    assert _get(server, '/server.py').status == 404


def test_root_returns_html(server):
    import dashboard.server as ds
    resp = _get(server, '/')
    if ds.HTML_PATH.exists():
        assert resp.status == 200
        assert 'text/html' in resp.getheader('Content-Type', '')
    else:
        assert resp.status == 404


def test_api_status_returns_json(server, monkeypatch):
    import dashboard.server as ds
    monkeypatch.setattr(ds, 'PLAN_PATH', Path('/nonexistent/plan.md'))
    resp = _get(server, '/api/status')
    assert resp.status == 200
    body = json.loads(resp.read())
    assert 'tasks' in body
    assert 'error' in body
