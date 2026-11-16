"""add projects table and project_id FK on sessions

Revision ID: 0005
Revises: db8522027afe
Create Date: 2026-07-07 01:30:00.000000

Rewritten in place (#946). The original upgrade added the foreign key with
``op.create_foreign_key``, which SQLite cannot do, so every database that
reached this revision without ``sessions.project_id`` (every v1.x install)
stopped here with NotImplementedError. SQLite databases that already ran it
are untouched: it only succeeded on them where the column already existed,
and both versions skip that case.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: str | None = 'db8522027afe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Create the projects table if it doesn't exist.
    if "projects" not in inspector.get_table_names():
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)

    # 2. Add project_id FK to sessions if the column doesn't exist.
    inspector = sa.inspect(bind)
    session_cols = {col["name"] for col in inspector.get_columns("sessions")}
    if "project_id" in session_cols:
        return
    # SQLite can add a column with its REFERENCES clause without rebuilding
    # a table that half the schema references.
    op.execute("ALTER TABLE sessions ADD COLUMN project_id INTEGER REFERENCES projects (id)")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # SQLite cannot drop a column that carries a foreign key, so batch mode
    # rebuilds sessions without it (env.py turns off FK enforcement for that).
    session_cols = {col["name"] for col in inspector.get_columns("sessions")}
    if "project_id" in session_cols:
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.drop_column("project_id")

    # Drop the projects table.
    if "projects" in inspector.get_table_names():
        op.drop_index(op.f("ix_projects_id"), table_name="projects")
        op.drop_table("projects")
