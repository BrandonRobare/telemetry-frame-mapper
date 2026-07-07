"""add projects table and project_id FK on sessions

Revision ID: 0005
Revises: db8522027afe
Create Date: 2026-07-07 01:30:00.000000

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
    if "project_id" not in session_cols:
        op.add_column("sessions", sa.Column("project_id", sa.Integer(), nullable=True))
        # Create FK after adding the column.
        session_names = inspector.get_foreign_keys("sessions")
        if not any(fk.get("referred_table") == "projects" for fk in session_names):
            op.create_foreign_key(
                "fk_sessions_project_id_projects",
                "sessions",
                "projects",
                ["project_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Remove FK and column from sessions.
    session_names = inspector.get_foreign_keys("sessions")
    for fk in session_names:
        if fk.get("referred_table") == "projects":
            name = fk["name"]
            if name is not None:
                op.drop_constraint(name, "sessions", type_="foreignkey")

    session_cols = {col["name"] for col in inspector.get_columns("sessions")}
    if "project_id" in session_cols:
        op.drop_column("sessions", "project_id")

    # Drop the projects table.
    if "projects" in inspector.get_table_names():
        op.drop_index(op.f("ix_projects_id"), table_name="projects")
        op.drop_table("projects")