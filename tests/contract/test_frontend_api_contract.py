"""Every backend call the frontend makes must reach a FastAPI route with that method.

The frontend builds API URLs as literals passed to the shared client helpers
(``get``/``post``/``patch``/``del`` from ``shared/api/client``) or to ``apiUrl()``,
which feeds links, ``window.open``, ``EventSource`` and raw ``fetch`` calls. This
test reads each literal URL and its HTTP method out of ``frontend/src`` and asks the
app's router whether it would dispatch that request. A control that GETs a
POST-only route — the survey report buttons answered 405 (#952) — fails here
instead of in front of an operator.

Calls whose URL is not a literal (a variable, or a helper that builds the path)
are skipped; they are out of this test's reach.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from starlette.routing import Match, Mount

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
CLIENT_MODULE = FRONTEND_SRC / "shared" / "api" / "client.ts"

# Client exports that take a URL as their first argument, and the method they send.
# ``apiUrl`` only builds a URL: it is a GET unless it is the URL of a ``fetch`` whose
# options name another method.
_URL_HELPERS = {"get": "GET", "post": "POST", "patch": "PATCH", "del": "DELETE", "apiUrl": None}
_NAMED_IMPORT = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")
_FETCH_BEFORE = re.compile(r"\bfetch\(\s*$")
_METHOD_OPTION = re.compile(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]")
# Stands in for each ``${...}`` in a template URL; a number also satisfies ``{id:int}``.
_PLACEHOLDER = "1"


@dataclass(frozen=True)
class FrontendCall:
    method: str
    url: str
    location: str

    @property
    def path(self) -> str:
        return re.split(r"[?#]", self.url, maxsplit=1)[0]


def _skip_string(src: str, i: int) -> int:
    """Return the index just past the quoted string that starts at ``src[i]``."""
    quote = src[i]
    i += 1
    while i < len(src) and src[i] != quote:
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _read_template(src: str, i: int) -> tuple[str, int]:
    """Read the template literal at ``src[i]``; each ``${...}`` becomes a placeholder."""
    text: list[str] = []
    i += 1
    while i < len(src) and src[i] != "`":
        if src[i] == "\\":
            text.append(src[i : i + 2])
            i += 2
        elif src.startswith("${", i):
            i = _skip_balanced(src, i + 1, "{", "}")
            text.append(_PLACEHOLDER)
        else:
            text.append(src[i])
            i += 1
    return "".join(text), i + 1


def _skip_balanced(src: str, i: int, open_char: str, close_char: str) -> int:
    """From the ``open_char`` at ``src[i]``, return the index just past its partner.

    Strings, template literals and comments are skipped, so brackets inside them
    do not count.
    """
    depth = 0
    while i < len(src):
        char = src[i]
        if char in "'\"":
            i = _skip_string(src, i)
            continue
        if char == "`":
            i = _read_template(src, i)[1]
            continue
        if src.startswith("//", i):
            i = src.find("\n", i)
            i = len(src) if i < 0 else i
            continue
        if src.startswith("/*", i):
            i = src.find("*/", i)
            i = len(src) if i < 0 else i + 2
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _read_url_literal(src: str, i: int) -> str | None:
    """Return the string or template literal at ``src[i]``, or None for an expression."""
    if i >= len(src):
        return None
    if src[i] in "'\"":
        end = _skip_string(src, i)
        return src[i + 1 : end - 1]
    if src[i] == "`":
        return _read_template(src, i)[0]
    return None


def _client_helpers(path: Path, src: str, client_module: Path) -> dict[str, str]:
    """Map each local name bound to a client URL helper in this file to the helper."""
    helpers: dict[str, str] = {}
    for names, spec in _NAMED_IMPORT.findall(src):
        if not spec.startswith("."):
            continue
        base = (path.parent / spec).resolve()
        candidates = (base.with_name(base.name + ".ts"), base.with_name(base.name + ".tsx"))
        if client_module.resolve() not in candidates:
            continue
        for spec_name in names.split(","):
            parts = spec_name.split(" as ")
            exported, local = parts[0].strip(), parts[-1].strip()
            if exported in _URL_HELPERS:
                helpers[local] = exported
    return helpers


def extract_calls(path: Path, src: str, client_module: Path = CLIENT_MODULE) -> list[FrontendCall]:
    """Find every literal URL this file hands to a client helper, with its method."""
    calls: list[FrontendCall] = []
    for local, helper in _client_helpers(path, src, client_module).items():
        for match in re.finditer(rf"(?<![\w$.]){re.escape(local)}\s*(?=[<(])", src):
            i = match.end()
            if src[i] == "<":  # A type argument, e.g. get<Job[]>(...)
                i = _skip_balanced(src, i, "<", ">")
            if i >= len(src) or src[i] != "(":
                continue
            args_start = i + 1
            while args_start < len(src) and src[args_start].isspace():
                args_start += 1
            url = _read_url_literal(src, args_start)
            if url is None or not url.startswith("/"):
                continue
            method = _URL_HELPERS[helper]
            if method is None:
                method = "GET"
                if _FETCH_BEFORE.search(src, 0, match.start()):
                    fetch_open = src.rindex("(", 0, match.start())
                    fetch_args = src[fetch_open : _skip_balanced(src, fetch_open, "(", ")")]
                    option = _METHOD_OPTION.search(fetch_args)
                    if option:
                        method = option.group(1).upper()
            line = src.count("\n", 0, match.start()) + 1
            calls.append(FrontendCall(method, url, f"{path.name}:{line}"))
    return calls


def frontend_api_calls() -> list[FrontendCall]:
    calls: list[FrontendCall] = []
    for path in sorted(FRONTEND_SRC.rglob("*.ts*")):
        if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
            continue
        calls.extend(extract_calls(path, path.read_text(encoding="utf-8")))
    return calls


def _dispatch(path: str, method: str) -> Match:
    """How the app's router matches a request, ignoring static-file mounts.

    Static mounts are skipped because the SPA mount answers any unmatched GET
    with index.html, which would hide a missing API route.
    """
    from backend.main import app

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "query_string": b"",
        "headers": [],
    }
    best = Match.NONE
    for route in app.router.routes:
        if isinstance(route, Mount):
            continue
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return Match.FULL
        best = max(best, match, key=lambda m: m.value)
    return best


def resolves(path: str, method: str) -> bool:
    """True when the app would handle ``method path`` rather than answer 404 or 405."""
    match = _dispatch(path, method)
    if match == Match.NONE and path != "/":
        # Starlette redirects (307, method kept) to the other trailing-slash form.
        match = _dispatch(path[:-1] if path.endswith("/") else f"{path}/", method)
    return match == Match.FULL


def test_extractor_reads_every_supported_call_form(tmp_path):
    client = tmp_path / "shared" / "api" / "client.ts"
    client.parent.mkdir(parents=True)
    client.write_text("export const get = () => null\n", encoding="utf-8")
    feature = tmp_path / "features" / "demo" / "Demo.tsx"
    feature.parent.mkdir(parents=True)
    source = """
import { apiUrl, get, post as send, del } from '../../shared/api/client'
import { get as otherGet } from './elsewhere'

const params = new URLSearchParams()
get<Record<string, number[]>>(`/items/${id}?${params.toString()}`)
send<{ ok: boolean }>(
  '/items/run', { value: `${a ? 'x' : 'y'}` },
)
del(`/items/${nested({ key: `${inner}` })}/child`)
otherGet('/not/the/client')
searchParams.get('/not/a/call')
get(pathVariable)
<a href={apiUrl(`/items/${id}/download`)}>x</a>
await fetch(apiUrl('/items/upload'), {
  // a comment with a quote ' and a paren (
  credentials: 'include',
  method: 'PUT',
})
new EventSource(apiUrl(`/items/${id}/events`))
"""
    calls = extract_calls(feature, source, client_module=client)

    assert sorted((call.method, call.url) for call in calls) == sorted(
        [
            ("GET", "/items/1?1"),
            ("POST", "/items/run"),
            ("DELETE", "/items/1/child"),
            ("GET", "/items/1/download"),
            ("PUT", "/items/upload"),
            ("GET", "/items/1/events"),
        ]
    )
    assert FrontendCall("GET", "/items/1?1", "x").path == "/items/1"


def test_router_check_tells_a_wrong_method_from_a_matching_route():
    assert resolves("/export/survey-report", "POST")
    assert not resolves("/export/survey-report", "DELETE")
    assert not resolves("/definitely/not/an/api/route", "GET")
    # Starlette redirects to the declared trailing-slash form, keeping the method.
    assert resolves("/target-areas", "GET")


def test_every_frontend_api_call_reaches_a_route_with_its_method():
    calls = frontend_api_calls()
    # A floor, so a change in how the frontend calls the API cannot make the
    # extractor silently find nothing and pass.
    assert len(calls) >= 80, f"only {len(calls)} frontend API calls were found"

    unresolved = sorted(
        f"{call.method} {call.url}  ({call.location})"
        for call in calls
        if not resolves(call.path, call.method)
    )
    assert not unresolved, (
        "These frontend calls have no FastAPI route for their method "
        "(the browser would get 404 or 405):\n  " + "\n  ".join(unresolved)
    )


def test_share_viewer_branches_on_the_error_code_the_backend_sends():
    """The password prompt keys off a machine-readable code, so both sides must agree."""
    from backend.routers.share_links import SHARE_PASSWORD_REQUIRED_CODE

    viewer = (FRONTEND_SRC / "features" / "share" / "ShareViewer.tsx").read_text(encoding="utf-8")
    assert f"'{SHARE_PASSWORD_REQUIRED_CODE}'" in viewer
