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
    if "parent_reconstruction_id" in columns:
        return
    if bind.dialect.name == "sqlite":
        # A plain add_column left upgraded databases without the self-FK that a
        # fresh schema has (#946). SQLite can add the column with its REFERENCES
        # clause in one ALTER, without rebuilding reconstructions.
        op.execute(
            "ALTER TABLE reconstructions ADD COLUMN parent_reconstruction_id INTEGER "
            "REFERENCES reconstructions (id)"
        )
    else:
        op.add_column(
            "reconstructions",
            sa.Column(
                "parent_reconstruction_id",
                sa.Integer(),
                sa.ForeignKey("reconstructions.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("reconstructions")}
    if "parent_reconstruction_id" in columns:
        # SQLite refuses to DROP a column that carries a foreign key, so batch
        # mode rebuilds the table without it (env.py turns off FK enforcement
        # for that, since other tables reference reconstructions).
        with op.batch_alter_table("reconstructions") as batch_op:
            batch_op.drop_column("parent_reconstruction_id")
