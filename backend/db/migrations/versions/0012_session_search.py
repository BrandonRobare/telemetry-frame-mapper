"""add SQLite FTS5 cross-session search (issue #390)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-17

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from backend.db.session_search import install_session_search_schema

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        install_session_search_schema(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for trigger in (
        "session_search_defects_ad",
        "session_search_defects_au",
        "session_search_defects_ai",
        "session_search_logs_ad",
        "session_search_logs_au",
        "session_search_logs_ai",
        "session_search_sessions_ad",
        "session_search_sessions_au",
        "session_search_sessions_ai",
    ):
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
    bind.exec_driver_sql("DROP TABLE IF EXISTS session_search")
