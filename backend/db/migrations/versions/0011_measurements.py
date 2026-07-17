"""add measurements table for persisted viewer measurements (issue #368)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "measurements" not in existing_tables:
        op.create_table(
            "measurements",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reconstruction_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("points_json", sa.Text(), nullable=False),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(), nullable=True),
            sa.Column("label", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["reconstruction_id"], ["reconstructions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_measurements_id"), "measurements", ["id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "measurements" in existing_tables:
        op.drop_index(op.f("ix_measurements_id"), table_name="measurements")
        op.drop_table("measurements")
