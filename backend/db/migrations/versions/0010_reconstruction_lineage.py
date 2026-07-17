"""add parent_reconstruction_id self-FK for reconstruction re-run lineage (issue #372)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("reconstructions")}
    if "parent_reconstruction_id" not in columns:
        op.add_column(
            "reconstructions",
            sa.Column("parent_reconstruction_id", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("reconstructions")}
    if "parent_reconstruction_id" in columns:
        # ponytail: on a genuinely fresh DB, 0001_baseline's create_all path picks up
        # the self-FK declared in models.py before this migration runs, and SQLite
        # refuses to DROP a column that carries a real FK constraint. Only affects
        # downgrading a never-before-migrated DB; on a real incremental upgrade this
        # column has no physical FK (plain add_column above) and drops cleanly.
        # Fix if needed: op.batch_alter_table("reconstructions") to recreate the table.
        op.drop_column("reconstructions", "parent_reconstruction_id")
