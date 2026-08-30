"""index the foreign-key columns used as query filters

Only the FK columns that actually appear in a WHERE clause are indexed, not all
29 declared in models.py. Deliberately skipped:

* the leading column of a composite primary key (``reconstruction_frames``,
  ``defect_images``, ``session_frame_selections``) — SQLite's implicit PK index
  already covers it;
* FK columns nothing filters on (``coverage_runs.target_area_id``,
  ``mission_plans.*``, ``share_link_unlock_sessions.share_link_id``,
  ``session_comparisons.*``, ``auto_import_records.session_id``).

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) -> index name is always ix_<table>_<column>, matching the
# name SQLAlchemy gives the same column's `index=True` on a fresh create_all().
_INDEXED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sessions", "project_id"),
    ("images", "session_id"),
    ("footprints", "image_id"),
    ("flight_logs", "session_id"),
    ("flight_log_points", "flight_log_id"),
    ("flight_entries", "session_id"),
    ("session_log_entries", "session_id"),
    ("reconstructions", "session_id"),
    ("reconstructions", "parent_reconstruction_id"),
    ("share_links", "reconstruction_id"),
    ("annotations", "reconstruction_id"),
    ("measurements", "reconstruction_id"),
    ("defects", "session_id"),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in _INDEXED_COLUMNS:
        if table not in tables:
            continue
        name = f"ix_{table}_{column}"
        if name in {index["name"] for index in inspector.get_indexes(table)}:
            continue
        op.create_index(name, table, [column], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in reversed(_INDEXED_COLUMNS):
        if table not in tables:
            continue
        name = f"ix_{table}_{column}"
        if name in {index["name"] for index in inspector.get_indexes(table)}:
            op.drop_index(name, table_name=table)
