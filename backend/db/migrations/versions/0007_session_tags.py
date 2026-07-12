"""add tags column to sessions for field organization (issue #369)

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
    columns = {c["name"] for c in inspector.get_columns("sessions")}
    if "tags" not in columns:
        op.add_column("sessions", sa.Column("tags", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("sessions")}
    if "tags" in columns:
        op.drop_column("sessions", "tags")
