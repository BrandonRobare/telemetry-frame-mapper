from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.routing import Match, Mount
from starlette.types import Scope

from backend.core.application_logging import configure_application_logging
from backend.core.config import (
    get_api_key_config,
    get_config,
    get_deployment_config,
    get_logging_config,
    get_pin_lock_config,
)
from backend.db.database import init_db
from backend.services.pin_lock import (
    create_session,
    record_unlock_failure,
    reset_unlock_attempts,
    session_is_valid,
    unlock_retry_after,
    valid_api_key,
    valid_pin,
)

from .routers import annotations as annotations_router
from .routers import auto_import as auto_import_router
from .routers import comparisons as comparisons_router
from .routers import coverage as coverage_router
from .routers import defects as defects_router
from .routers import export as export_router
from .routers import flight_entries as flight_entries_router
from .routers import flight_log as flight_log_router
from .routers import footprints as footprints_router
from .routers import georeferencing as georeferencing_router
from .routers import images as images_router
from .routers import jobs as jobs_router
from .routers import measurements as measurements_router
from .routers import metrics as metrics_router
from .routers import plans as plans_router
from .routers import projects as projects_router
from .routers import reconstruction as reconstruction_router
from .routers import session_log as session_log_router
from .routers import sessions as sessions_router
from .routers import settings as settings_router
from .routers import share_links as share_links_router
from .routers import srt as srt_router
from .routers import storage as storage_router
from .routers import system as system_router
from .routers import target_areas as target_areas_router
from .routers import tiles as tiles_router
from .routers import uploads as uploads_router
from .routers import webodm as webodm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_application_logging(get_logging_config())
    init_db()
    from backend.services.artifact_backup_schedule import scheduled_backup_from_config
    from backend.services.auto_import import AutoImportWatcher
    from backend.services.job_queue import shutdown_worker, start_worker
    from backend.services.orthomosaic_export import reset_dangling_ortho_status

    owns_job_queue = start_worker()
    if not owns_job_queue and pin_lock_config["enabled"]:
        raise RuntimeError(
            "PIN lock requires a single API process; another process already owns the job "
            "queue lock."
        )
    if owns_job_queue:
        # Same startup-recovery pass as the job-queue reaper, and gated on the same
        # lock so a second process cannot fail another's in-flight export (#628).
        reaped = reset_dangling_ortho_status()
        if reaped:
            logging.getLogger("backend").info(
                "Recovered %d orphaned orthomosaic export(s) on startup", reaped
            )

    watcher = AutoImportWatcher()
    app.state.auto_import_watcher = watcher
    watcher.start()
    backup_scheduler = scheduled_backup_from_config(get_config())
    app.state.backup_scheduler = backup_scheduler
    backup_scheduler.start()
    if shutil.which("colmap") is None:
        logging.getLogger("backend").warning(
            "COLMAP not found on PATH — reconstruction jobs will fail until it is installed "
            "(see docs/INSTALL.md)"
        )
    try:
        yield
    finally:
        backup_scheduler.stop()
        watcher.stop()
        shutdown_worker(timeout=10.0)


app = FastAPI(title="Telemetry Frame Mapper API", version="2.0.3", lifespan=lifespan)
app.include_router(sessions_router.router)
app.include_router(target_areas_router.router)
app.include_router(coverage_router.router)
app.include_router(flight_log_router.router)
app.include_router(flight_entries_router.router)
app.include_router(srt_router.router)
app.include_router(plans_router.router)
app.include_router(projects_router.router)
app.include_router(images_router.router)
app.include_router(export_router.router)
app.include_router(georeferencing_router.router)
app.include_router(session_log_router.router)
app.include_router(footprints_router.router)
app.include_router(reconstruction_router.router)
app.include_router(annotations_router.router)
app.include_router(auto_import_router.router)
app.include_router(measurements_router.router)
app.include_router(metrics_router.router)
app.include_router(defects_router.router)
app.include_router(comparisons_router.router)
app.include_router(system_router.router)
app.include_router(jobs_router.router)
app.include_router(storage_router.router)
app.include_router(settings_router.router)
app.include_router(uploads_router.router)
app.include_router(share_links_router.router)
app.include_router(webodm_router.router)
app.include_router(tiles_router.router)

deployment_config = get_deployment_config()
pin_lock_config = get_pin_lock_config()
api_key_config = get_api_key_config()
app.state.pin_lock_sessions = {}
app.state.pin_unlock_attempts = {}
app.state.share_unlock_attempts = {}
app.add_middleware(
    CORSMiddleware,
    allow_origins=deployment_config["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORS does not stop DNS rebinding: an attacker page on a domain that re-resolves to
# 127.0.0.1 becomes same-origin with a loopback-bound API, and every route here is
# unauthenticated by default. Pinning the Host header closes that — browsers cannot set
# Host, so only a request genuinely addressed to one of these names is served.
if deployment_config["allowed_hosts"]:
    _allowed_hosts = set(deployment_config["allowed_hosts"])
else:
    _allowed_hosts = {"localhost", "127.0.0.1", "::1", "testserver", deployment_config["host"]}
    for _origin in deployment_config["cors_origins"]:
        _origin_host = urlparse(_origin).hostname
        if _origin_host:
            _allowed_hosts.add(_origin_host)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(_allowed_hosts))

processed_dir = os.path.abspath(get_config().processed_dir)
os.makedirs(processed_dir, exist_ok=True)
app.mount("/processed", StaticFiles(directory=processed_dir), name="processed")


@app.get("/health")
def health():
    return {"status": "ok"}


PIN_LOCK_COOKIE_NAME = "tfm_pin_unlock"
PIN_LOCK_OPEN_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/pin-lock/status",
    "/pin-lock/unlock",
}
PIN_LOCK_SHARE_SHELL_RESOURCES = {
    "/favicon.ico",
    "/favicon.svg",
    "/manifest.webmanifest",
    "/pwa-icon-maskable.svg",
    "/pwa-icon.svg",
}


def _pin_lock_open_path(path: str) -> bool:
    return (
        path in PIN_LOCK_OPEN_PATHS
        or path in PIN_LOCK_SHARE_SHELL_RESOURCES
        or path.startswith("/assets/")
        or path.startswith("/docs/")
        or path.startswith("/redoc/")
        or path == "/share"
        or path.startswith("/share/")
        or path == "/view/share"
        or path.startswith("/view/share/")
    )


def _cookie_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return request.url.scheme == "https" or forwarded.lower() == "https"


@app.middleware("http")
async def require_pin_unlock(request: Request, call_next):
    api_key = request.headers.get("X-Drone-Mapping-Key")
    api_key_is_valid = (
        api_key_config["enabled"]
        and isinstance(api_key, str)
        and valid_api_key(api_key, os.environ[api_key_config["key_hash_env"]])
    )
    if (
        not pin_lock_config["enabled"]
        or _pin_lock_open_path(request.url.path)
        or api_key_is_valid
        or session_is_valid(app.state.pin_lock_sessions, request.cookies.get(PIN_LOCK_COOKIE_NAME))
    ):
        return await call_next(request)
    return Response(
        status_code=401,
        content='{"detail":"PIN unlock required"}',
        media_type="application/json",
    )


@app.get("/pin-lock/status")
def pin_lock_status():
    """Expose only whether the local lock is enabled, never its configuration or hash."""
    return {"enabled": pin_lock_config["enabled"]}


@app.post("/pin-lock/unlock", status_code=204)
def unlock_pin_lock(body: dict[str, str], request: Request, response: Response):
    """Verify the configured scrypt PIN and issue a short-lived HttpOnly cookie."""
    if not pin_lock_config["enabled"]:
        raise HTTPException(status_code=404, detail="PIN lock is not enabled")
    client = request.client.host if request.client else "unknown"
    retry_after = unlock_retry_after(app.state.pin_unlock_attempts, client)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts",
            headers={"Retry-After": str(retry_after)},
        )
    pin = body.get("pin")
    pin_hash = os.environ[pin_lock_config["pin_hash_env"]]
    if not isinstance(pin, str) or not valid_pin(pin, pin_hash):
        record_unlock_failure(app.state.pin_unlock_attempts, client)
        raise HTTPException(status_code=403, detail="Incorrect PIN")
    reset_unlock_attempts(app.state.pin_unlock_attempts, client)
    token = create_session(app.state.pin_lock_sessions, pin_lock_config["session_ttl"])
    response.set_cookie(
        PIN_LOCK_COOKIE_NAME,
        token,
        max_age=pin_lock_config["session_ttl"],
        path="/",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
    )


class SPAStaticFiles(StaticFiles):
    """Serve built static assets, falling back to index.html for unmatched
    paths so client-side routes (e.g. /some/react-route) don't 404."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


class FrontendMount(Mount):
    """A "/" mount that defers to API routes and Starlette's redirect-slash
    handling instead of unconditionally swallowing every path.

    A plain Mount("/") matches every path regardless of HTTP method, which
    would shadow API routers that rely on Starlette's redirect-slash
    behavior (e.g. a route declared as "/target-areas/" being reached via
    a request to "/target-areas" with no trailing slash). Since Mount
    matching only looks at the path — not the method or whether a redirect
    would otherwise apply — it would intercept those requests (returning
    405 for writes, or serving index.html for reads) before the router
    ever got a chance to redirect to the slash-suffixed route.

    To avoid that, this mount declines (Match.NONE) for any request whose
    path, with a trailing slash appended, would match one of the app's own
    routes — letting the normal API route (and its redirect-slash
    behavior) win instead.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope.get("type") == "http":
            if scope.get("method") not in ("GET", "HEAD"):
                return Match.NONE, {}
            path = scope.get("path", "")
            if path and not path.endswith("/"):
                redirect_scope = {**scope, "path": path + "/"}
                for route in app.router.routes:
                    if route is self:
                        continue
                    if route.matches(redirect_scope)[0] != Match.NONE:
                        return Match.NONE, {}
        return super().matches(scope)


frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    frontend_static = SPAStaticFiles(directory=str(frontend_dist), html=True)
    app.router.routes.append(FrontendMount("/", app=frontend_static, name="frontend"))
else:
    logging.getLogger("backend").info(
        "frontend/dist not found - run 'npm run build' in frontend/ to serve the UI "
        "from the backend on one process, or use 'npm run dev' for development."
    )
