"""record effective Gaussian-splat trainer settings

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("reconstructions")
    }
    if "effective_splat_settings" in columns:
        return
    op.add_column(
        "reconstructions",
        sa.Column("effective_splat_settings", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("reconstructions")
    }
    if "effective_splat_settings" in columns:
        op.drop_column("reconstructions", "effective_splat_settings")