"""add flight_entries table for operator battery/flight records

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "flight_entries" in inspector.get_table_names():
        return
    op.create_table(
        "flight_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("battery_id", sa.String(), nullable=True),
        sa.Column("start_pct", sa.Float(), nullable=True),
        sa.Column("end_pct", sa.Float(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_flight_entries_id"), "flight_entries", ["id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "flight_entries" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_flight_entries_id"), table_name="flight_entries")
    op.drop_table("flight_entries")
