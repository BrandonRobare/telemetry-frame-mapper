#!/usr/bin/env python3
"""
DroneGIS Development Dashboard Server
--------------------------------------
Stdlib only — no pip install needed. Works on Python 3.9+.

Usage:
    python dashboard/server.py

Open: http://localhost:7000
"""
import http.server
import json
import os
import queue
import re
import threading
import time
from pathlib import Path

PORT = 7000
PLAN_PATH = Path(__file__).parent.parent / "docs/superpowers/plans/2026-04-26-drone-mapping-mvp.md"
HTML_PATH  = Path(__file__).parent / "index.html"

# markdown parser

def parse_plan(text: str) -> list:
    """Parse the implementation plan markdown and return a list of task dicts."""
    tasks = []
    current = None
    in_files_block = False

    for line in text.splitlines():
        # task heading: ## Task N: Name
        m = re.match(r'^## Task (\d+[a-z]?): (.+)', line)
        if m:
            if current:
                _finalize(current)
                tasks.append(current)
            raw_name = m.group(2)
            current = {
                'number': m.group(1),          # string — could be "11b"
                'name':   raw_name.replace('🤖', '').strip(),
                'codex':  '🤖' in raw_name,
                'steps':  [],
                'files':  [],
                'status': 'pending',
                'progress': {'done': 0, 'total': 0},
            }
            in_files_block = False
            continue

        if current is None:
            continue

        # files line: **Files:** path, path
        if line.startswith('**Files:**'):
            in_files_block = True
            current['files'] += _extract_paths(line)
            continue

        if in_files_block:
            paths = _extract_paths(line)
            if paths:
                current['files'] += paths
            # Stop files block on blank line or new section marker
            if line.strip() == '' or line.startswith('- [ ]') or line.startswith('- [x]') \
                    or line.startswith('**') or line.startswith('##'):
                in_files_block = False

        # step: - [ ] **Label** or - [x] **Label**
        sm = re.match(r'^- \[([ x])\] \*\*(.+?)\*\*', line)
        if sm:
            current['steps'].append({
                'checked': sm.group(1) == 'x',
                'label':   sm.group(2),
            })

    if current:
        _finalize(current)
        tasks.append(current)

    return tasks


def _extract_paths(line: str) -> list:
    """Pull backtick-quoted paths from a line."""
    return re.findall(r'`([^`]+\.[a-zA-Z]{1,10})`', line)


def _finalize(task: dict):
    """Compute status and progress; deduplicate files."""
    steps  = task['steps']
    total  = len(steps)
    done   = sum(1 for s in steps if s['checked'])
    task['progress'] = {'done': done, 'total': total}

    if total == 0 or done == 0:
        task['status'] = 'pending'
    elif done == total:
        task['status'] = 'complete'
    else:
        task['status'] = 'in-progress'

    seen = set()
    deduped = []
    for f in task['files']:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    task['files'] = deduped


def get_status() -> dict:
    """Read and parse the plan file; return full status payload."""
    try:
        text = PLAN_PATH.read_text(encoding='utf-8')
    except FileNotFoundError:
        return {
            'tasks': [],
            'summary': {},
            'error': f'Plan file not found: {PLAN_PATH}',
            'updated_at': time.strftime('%H:%M:%S'),
        }

    tasks = parse_plan(text)

    total_steps = sum(t['progress']['total'] for t in tasks)
    done_steps  = sum(t['progress']['done']  for t in tasks)
    complete    = sum(1 for t in tasks if t['status'] == 'complete')
    in_progress = sum(1 for t in tasks if t['status'] == 'in-progress')

    return {
        'tasks': tasks,
        'summary': {
            'total_tasks':       len(tasks),
            'complete_tasks':    complete,
            'in_progress_tasks': in_progress,
            'pending_tasks':     len(tasks) - complete - in_progress,
            'total_steps':       total_steps,
            'done_steps':        done_steps,
        },
        'updated_at': time.strftime('%H:%M:%S'),
    }


# SSE broadcast

_subscribers: list = []
_sub_lock = threading.Lock()


class _SSEQueue:
    """Per-client message queue for SSE streaming."""
    def __init__(self):
        self._q: queue.Queue = queue.Queue()

    def put(self, item: str):
        self._q.put(item)

    def get(self, timeout: float = 30.0) -> str:
        return self._q.get(timeout=timeout)


def _broadcast():
    """Push a statusUpdate event to every connected SSE client."""
    payload = json.dumps(get_status(), ensure_ascii=False)
    data = f'event: statusUpdate\ndata: {payload}\n\n'
    with _sub_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put(data)
            except Exception:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)


def _watch_loop():
    """Background thread: poll the plan file mtime; broadcast on change."""
    last_mtime = 0.0
    first = True
    while True:
        try:
            mtime = PLAN_PATH.stat().st_mtime
            if mtime != last_mtime:
                if not first:          # skip the very first read
                    _broadcast()
                last_mtime = mtime
                first = False
        except FileNotFoundError:
            pass
        time.sleep(1.5)


# HTTP handler

class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log
        pass

    def do_GET(self):
        path = self.path.split('?')[0]  # ignore query string
        if path in ('/', '/index.html'):
            self._serve_file(HTML_PATH, 'text/html; charset=utf-8')
        elif path == '/api/status':
            self._json_response(get_status())
        elif path == '/api/events':
            self._sse_stream()
        else:
            self.send_error(404, 'Not found')

    # helpers

    def _serve_file(self, path: Path, content_type: str):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, f'File not found: {path}')
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def _sse_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('X-Accel-Buffering', 'no')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        client_q = _SSEQueue()
        with _sub_lock:
            _subscribers.append(client_q)

        # Send initial state immediately
        try:
            payload = json.dumps(get_status(), ensure_ascii=False)
            self.wfile.write(f'event: statusUpdate\ndata: {payload}\n\n'.encode('utf-8'))
            self.wfile.flush()
        except Exception:
            with _sub_lock:
                _subscribers.remove(client_q)
            return

        # Stream loop — heartbeat every 30 s to keep connection alive
        while True:
            try:
                msg = client_q.get(timeout=30.0)
                self.wfile.write(msg.encode('utf-8'))
                self.wfile.flush()
            except queue.Empty:
                try:
                    self.wfile.write(b': heartbeat\n\n')
                    self.wfile.flush()
                except Exception:
                    break
            except Exception:
                break

        with _sub_lock:
            try:
                _subscribers.remove(client_q)
            except ValueError:
                pass


# entry point

if __name__ == '__main__':
    # Start file watcher
    t = threading.Thread(target=_watch_loop, daemon=True)
    t.start()

    server = http.server.ThreadingHTTPServer(('', PORT), _Handler)
    print(f'\n  DroneGIS Dev Dashboard')
    print(f'  http://localhost:{PORT}')
    print(f'  Plan: {PLAN_PATH}')
    print(f'  Edit checkboxes in the plan file to see live updates.\n')
    print('  Press Ctrl-C to stop.\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Stopped.')
