from __future__ import annotations

import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.routing import Match, Mount
from starlette.types import Scope

from backend.core.config import get_config
from backend.db.database import init_db

from .routers import annotations as annotations_router
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
from .routers import uploads as uploads_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from backend.services.job_queue import claim_stale_jobs, shutdown_worker, start_worker

    claimed = claim_stale_jobs()
    if claimed:
        logging.getLogger("backend").info(
            "JobQueue: marked %d orphaned running jobs as failed", claimed
        )
    start_worker()
    if shutil.which("colmap") is None:
        logging.getLogger("backend").warning(
            "COLMAP not found on PATH — reconstruction jobs will fail until it is installed "
            "(see docs/INSTALL.md)"
        )
    yield
    shutdown_worker(timeout=10.0)


app = FastAPI(title="Drone Mapping API", version="1.0.0", lifespan=lifespan)
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
app.include_router(defects_router.router)
app.include_router(comparisons_router.router)
app.include_router(system_router.router)
app.include_router(jobs_router.router)
app.include_router(storage_router.router)
app.include_router(settings_router.router)
app.include_router(uploads_router.router)
app.include_router(share_links_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processed_dir = os.path.abspath(get_config().processed_dir)
os.makedirs(processed_dir, exist_ok=True)
app.mount("/processed", StaticFiles(directory=processed_dir), name="processed")


@app.get("/health")
def health():
    return {"status": "ok"}


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
