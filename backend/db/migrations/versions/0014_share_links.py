"""add persisted, revocable share links (issue #376)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-17

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "share_links" not in tables:
        op.create_table(
            "share_links",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("reconstruction_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["reconstruction_id"], ["reconstructions.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(op.f("ix_share_links_id"), "share_links", ["id"], unique=False)
        op.create_index(
            op.f("ix_share_links_token_hash"), "share_links", ["token_hash"], unique=True
        )
    if "share_link_unlock_sessions" not in tables:
        op.create_table(
            "share_link_unlock_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("share_link_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(
            op.f("ix_share_link_unlock_sessions_id"),
            "share_link_unlock_sessions",
            ["id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_share_link_unlock_sessions_token_hash"),
            "share_link_unlock_sessions",
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "share_link_unlock_sessions" in tables:
        op.drop_index(
            op.f("ix_share_link_unlock_sessions_token_hash"),
            table_name="share_link_unlock_sessions",
        )
        op.drop_index(
            op.f("ix_share_link_unlock_sessions_id"), table_name="share_link_unlock_sessions"
        )
        op.drop_table("share_link_unlock_sessions")
    if "share_links" in tables:
        op.drop_index(op.f("ix_share_links_token_hash"), table_name="share_links")
        op.drop_index(op.f("ix_share_links_id"), table_name="share_links")
        op.drop_table("share_links")
