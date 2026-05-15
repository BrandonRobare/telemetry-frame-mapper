from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db.database import init_db

from .routers import coverage as coverage_router
from .routers import export as export_router
from .routers import flight_log as flight_log_router
from .routers import footprints as footprints_router
from .routers import images as images_router
from .routers import jobs as jobs_router
from .routers import plans as plans_router
from .routers import reconstruction as reconstruction_router
from .routers import session_log as session_log_router
from .routers import sessions as sessions_router
from .routers import srt as srt_router
from .routers import storage as storage_router
from .routers import system as system_router
from .routers import target_areas as target_areas_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Drone Mapping API", version="0.1.0", lifespan=lifespan)
app.include_router(sessions_router.router)
app.include_router(target_areas_router.router)
app.include_router(coverage_router.router)
app.include_router(flight_log_router.router)
app.include_router(srt_router.router)
app.include_router(plans_router.router)
app.include_router(images_router.router)
app.include_router(export_router.router)
app.include_router(session_log_router.router)
app.include_router(footprints_router.router)
app.include_router(reconstruction_router.router)
app.include_router(system_router.router)
app.include_router(jobs_router.router)
app.include_router(storage_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processed_dir = os.path.abspath("./processed")
os.makedirs(processed_dir, exist_ok=True)
app.mount("/processed", StaticFiles(directory=processed_dir), name="processed")


@app.get("/health")
def health():
    return {"status": "ok"}

