"""add durable auto-import dedupe records (issue #371)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "auto_import_records" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "auto_import_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(
        op.f("ix_auto_import_records_id"), "auto_import_records", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_auto_import_records_fingerprint"),
        "auto_import_records",
        ["fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    if "auto_import_records" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index(op.f("ix_auto_import_records_fingerprint"), table_name="auto_import_records")
    op.drop_index(op.f("ix_auto_import_records_id"), table_name="auto_import_records")
    op.drop_table("auto_import_records")
