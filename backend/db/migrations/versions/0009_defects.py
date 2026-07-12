"""add defects and defect_images tables for field defect flagging (issue #387)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "defects" not in existing_tables:
        op.create_table(
            "defects",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_defects_id"), "defects", ["id"], unique=False)

    if "defect_images" not in inspector.get_table_names():
        op.create_table(
            "defect_images",
            sa.Column("defect_id", sa.Integer(), nullable=False),
            sa.Column("image_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["defect_id"], ["defects.id"]),
            sa.ForeignKeyConstraint(["image_id"], ["images.id"]),
            sa.PrimaryKeyConstraint("defect_id", "image_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "defect_images" in existing_tables:
        op.drop_table("defect_images")
    if "defects" in existing_tables:
        op.drop_index(op.f("ix_defects_id"), table_name="defects")
        op.drop_table("defects")
