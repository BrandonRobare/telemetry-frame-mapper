"""add DJI flight log columns (v2.0 platform import)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLIGHT_LOG_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "log_version": sa.Integer(),
    "aircraft_name": sa.String(),
    "aircraft_sn": sa.String(),
    "encrypted": sa.Boolean(),
}

_FLIGHT_LOG_POINT_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "roll": sa.Float(),
    "pitch": sa.Float(),
    "yaw": sa.Float(),
    "gimbal_pitch": sa.Float(),
    "gimbal_roll": sa.Float(),
    "gimbal_yaw": sa.Float(),
    "battery_voltage": sa.Float(),
    "battery_charge_pct": sa.Float(),
    "battery_temperature_c": sa.Float(),
}

_COLUMNS_BY_TABLE = {
    "flight_logs": _FLIGHT_LOG_COLUMNS,
    "flight_log_points": _FLIGHT_LOG_POINT_COLUMNS,
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, cols in _COLUMNS_BY_TABLE.items():
        if table not in existing_tables:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        for name, col_type in cols.items():
            if name not in existing_cols:
                op.add_column(table, sa.Column(name, col_type))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, cols in reversed(list(_COLUMNS_BY_TABLE.items())):
        if table not in existing_tables:
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        for name in reversed(cols):
            if name in existing_cols:
                op.drop_column(table, name)