from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.database import get_db

router = APIRouter(tags=["operations"])
_PROCESS_START_TIME = time.time()


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request, db: Session = Depends(get_db)) -> Response:
    """Expose cheap, local Prometheus scrape signals without user-data labels."""
    try:
        db.execute(text("SELECT 1"))
        database_up = 1
    except SQLAlchemyError:
        database_up = 0
    body = "\n".join(
        (
            "# HELP drone_mapping_build_info Application build information.",
            "# TYPE drone_mapping_build_info gauge",
            f'drone_mapping_build_info{{version="{request.app.version}"}} 1',
            "# HELP drone_mapping_process_start_time_seconds Unix time when this process started.",
            "# TYPE drone_mapping_process_start_time_seconds gauge",
            f"drone_mapping_process_start_time_seconds {_PROCESS_START_TIME}",
            "# HELP drone_mapping_database_up Whether a lightweight database probe succeeds.",
            "# TYPE drone_mapping_database_up gauge",
            f"drone_mapping_database_up {database_up}",
            "",
        )
    )
    return Response(body, media_type="text/plain; version=0.0.4; charset=utf-8")
