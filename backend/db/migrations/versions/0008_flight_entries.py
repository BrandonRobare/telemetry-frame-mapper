"""add flight_entries table for battery/flight metadata tracker (issue #401)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "flight_entries" not in inspector.get_table_names():
        op.create_table(
            "flight_entries",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
            sa.Column("battery_id", sa.String(), nullable=True),
            sa.Column("start_pct", sa.Float(), nullable=True),
            sa.Column("end_pct", sa.Float(), nullable=True),
            sa.Column("duration_s", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "flight_entries" in inspector.get_table_names():
        op.drop_table("flight_entries")
