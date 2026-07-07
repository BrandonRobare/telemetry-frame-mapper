"""add source_session_ids column for multi-session reconstruction

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("reconstructions")}
    if "source_session_ids" not in columns:
        op.add_column("reconstructions", sa.Column("source_session_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("reconstructions")}
    if "source_session_ids" in columns:
        op.drop_column("reconstructions", "source_session_ids")