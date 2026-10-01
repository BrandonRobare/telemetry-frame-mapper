"""give the delete-path foreign keys ON DELETE SET NULL (issue #945)

Deleting an auto-imported session, or a reconstruction with a dense re-run child,
failed on a foreign key after its files were already gone. The schema now says what
a delete does to these references instead of leaving it to call order:

* ``auto_import_records.session_id`` -> ``ON DELETE SET NULL`` (and nullable): the
  import claim outlives its session, so the watcher does not import the folder again.
* ``reconstructions.parent_reconstruction_id`` -> ``ON DELETE SET NULL``: a re-run
  keeps its own artifacts, so deleting its parent only detaches it.

``session_comparisons`` keeps its plain foreign keys on purpose: deleting what a
comparison uses is refused rather than silently deleting the comparison.

SQLite cannot alter a foreign key in place, so both tables are rebuilt with batch
mode. That rebuild drops the old table, and with foreign-key enforcement on (the app's
engine turns it on for every connection) the drop runs an implicit DELETE that fails
on, or cascades into, every row referencing the table. The rebuild therefore runs with
enforcement off, inside one transaction, checks that it broke no reference, and turns
enforcement back on before the connection goes back to the app's pool.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reflected SQLite foreign keys are unnamed; batch mode needs a name to drop one.
_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}

# (table, column, referred table, ON DELETE action after upgrade, nullable after upgrade)
_RULES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("auto_import_records", "session_id", "sessions", "SET NULL", True),
    ("reconstructions", "parent_reconstruction_id", "reconstructions", "SET NULL", True),
)


def _column_state(inspector, table: str, column: str) -> tuple[str | None, bool]:
    """Return (ON DELETE action, nullable) for a single-column foreign key."""
    ondelete = None
    for fk in inspector.get_foreign_keys(table):
        if fk["constrained_columns"] == [column]:
            ondelete = (fk.get("options") or {}).get("ondelete")
    nullable = next(c["nullable"] for c in inspector.get_columns(table) if c["name"] == column)
    return (ondelete.upper() if ondelete else None), bool(nullable)


def _foreign_key_violations(raw) -> set[tuple]:
    # (table, rowid, parent table); the fkid column changes when a table is rebuilt.
    return {tuple(row[:3]) for row in raw.execute("PRAGMA foreign_key_check").fetchall()}


@contextmanager
def _sqlite_rebuild_guard() -> Iterator[None]:
    """Run table rebuilds atomically with SQLite foreign-key enforcement off."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        yield
        return
    raw = bind.connection.driver_connection
    enforced = bool(raw.execute("PRAGMA foreign_keys").fetchone()[0])
    if enforced:
        raw.execute("PRAGMA foreign_keys=OFF")
        if raw.execute("PRAGMA foreign_keys").fetchone()[0]:
            # The pragma is a no-op inside a transaction; rebuilding with enforcement
            # on would cascade into or fail on every referencing row.
            raise RuntimeError(
                "Could not turn off SQLite foreign-key enforcement to rebuild tables for "
                "revision 0018, so the database was left unchanged."
            )
    began = not raw.in_transaction
    try:
        before = _foreign_key_violations(raw)
        if began:
            raw.execute("BEGIN")
        yield
        broken = _foreign_key_violations(raw) - before
        if broken:
            raise RuntimeError(f"Revision 0018 would break foreign keys: {sorted(broken)}")
        if began:
            raw.commit()
    except BaseException:
        if began:
            raw.rollback()
        raise
    finally:
        if enforced:
            raw.execute("PRAGMA foreign_keys=ON")


def _rebuild(
    table: str, column: str, referred: str, ondelete: str | None, nullable: bool
) -> None:
    with op.batch_alter_table(
        table, recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(f"fk_{table}_{column}_{referred}", type_="foreignkey")
        batch_op.alter_column(column, existing_type=sa.Integer(), nullable=nullable)
        batch_op.create_foreign_key(
            f"fk_{table}_{column}_{referred}", referred, [column], ["id"], ondelete=ondelete
        )


def _pending(targets) -> list[tuple[str, str, str, str | None, bool]]:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    return [
        (table, column, referred, ondelete, nullable)
        for table, column, referred, ondelete, nullable in targets
        if table in tables and _column_state(inspector, table, column) != (ondelete, nullable)
    ]


def upgrade() -> None:
    pending = _pending(_RULES)
    if not pending:
        return
    with _sqlite_rebuild_guard():
        # Apply the new rule to references that already dangle (possible in databases
        # written before enforcement was on), so the rebuilt tables start consistent.
        op.execute(
            "UPDATE auto_import_records SET session_id = NULL "
            "WHERE session_id IS NOT NULL AND session_id NOT IN (SELECT id FROM sessions)"
        )
        op.execute(
            "UPDATE reconstructions SET parent_reconstruction_id = NULL "
            "WHERE parent_reconstruction_id IS NOT NULL "
            "AND parent_reconstruction_id NOT IN (SELECT id FROM reconstructions)"
        )
        for rule in pending:
            _rebuild(*rule)


def downgrade() -> None:
    pending = _pending(
        (table, column, referred, None, table != "auto_import_records")
        for table, column, referred, _ondelete, _nullable in _RULES
    )
    if not pending:
        return
    with _sqlite_rebuild_guard():
        # A claim whose session was deleted cannot satisfy the old NOT NULL column.
        op.execute("DELETE FROM auto_import_records WHERE session_id IS NULL")
        for rule in pending:
            _rebuild(*rule)
