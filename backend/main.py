from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db.database import init_db

app = FastAPI(title="Drone Mapping API", version="0.1.0")

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


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers added in later tasks
