from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db.database import init_db
from .routers import sessions as sessions_router
from .routers import target_areas as target_areas_router
from .routers import coverage as coverage_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Drone Mapping API", version="0.1.0", lifespan=lifespan)
app.include_router(sessions_router.router)
app.include_router(target_areas_router.router)
app.include_router(coverage_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

thumbs_dir = os.path.abspath("./processed/thumbs")
os.makedirs(thumbs_dir, exist_ok=True)
app.mount("/thumbs", StaticFiles(directory=thumbs_dir), name="thumbs")


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers added in later tasks
