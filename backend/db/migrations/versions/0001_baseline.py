"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-06-22

Idempotent baseline migration. Handles two cases in one pass:

1. A genuinely fresh database with no tables at all: every table in the
   frozen ``_BASELINE`` schema below is created.
2. An existing database created by the old hand-rolled
   ``_ensure_sqlite_schema`` / ``create_all`` path (v1.0.0), which already has
   most tables but may be missing columns that were introduced before Alembic
   had explicit owner revisions. Missing tables come from ``_BASELINE``, and
   only the columns that are actually missing are added.

Every operation is conditional on the current DB state via
``sa.inspect``, so re-running this migration (or running it against a
database that already matches the target schema) is a no-op.

Frozen schema (#946): this revision used to create its tables from the live
``Base.metadata``, so a fresh ``alembic upgrade head`` silently followed every
edit to models.py, whether or not a revision recorded it, and fresh and
upgraded databases could drift apart. ``_BASELINE`` is the exact schema that
code created, written out as it stood at revision 0017, and must not change
again: a schema change goes in a new revision, which then has to work on fresh
databases too. tests/backend/test_database.py checks that a fresh upgrade
still builds what the models describe.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The schema as of revision 0017. Model-independent on purpose; see the module
# docstring before touching it.
_BASELINE = sa.MetaData()

sa.Table(
    "job_queue",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("job_type", sa.String(), nullable=False),
    sa.Column("target_id", sa.Integer(), nullable=False),
    sa.Column("status", sa.String()),
    sa.Column("priority", sa.Integer()),
    sa.Column("payload_json", sa.Text()),
    sa.Column("error_msg", sa.String()),
    sa.Column("attempt", sa.Integer()),
    sa.Column("max_attempts", sa.Integer()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("started_at", sa.DateTime()),
    sa.Column("completed_at", sa.DateTime()),
    sa.Index("ix_job_queue_id", "id"),
)

sa.Table(
    "projects",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("description", sa.Text()),
    sa.Column("created_at", sa.DateTime()),
    sa.UniqueConstraint("name"),
    sa.Index("ix_projects_id", "id"),
)

sa.Table(
    "target_areas",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String()),
    sa.Column("geom_geojson", sa.Text()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("notes", sa.Text()),
    sa.Index("ix_target_areas_id", "id"),
)

sa.Table(
    "coverage_runs",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("target_area_id", sa.Integer(), sa.ForeignKey("target_areas.id"), nullable=False),
    sa.Column("session_ids", sa.Text()),
    sa.Column("total_area_m2", sa.Float()),
    sa.Column("covered_area_m2", sa.Float()),
    sa.Column("coverage_pct", sa.Float()),
    sa.Column("gap_geojson", sa.Text()),
    sa.Column("overlap_geojson", sa.Text()),
    sa.Column("run_at", sa.DateTime()),
    sa.Index("ix_coverage_runs_id", "id"),
)

sa.Table(
    "sessions",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(), nullable=False),
    sa.Column("folder_path", sa.String()),
    sa.Column("import_mode", sa.String()),
    sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id")),
    sa.Column("imported_at", sa.DateTime()),
    sa.Column("photo_count", sa.Integer()),
    sa.Column("usable_count", sa.Integer()),
    sa.Column("notes", sa.Text()),
    sa.Column("tags", sa.Text()),
    sa.Index("ix_sessions_id", "id"),
    sa.Index("ix_sessions_project_id", "project_id"),
)

sa.Table(
    "auto_import_records",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("fingerprint", sa.String(), nullable=False),
    sa.Column("source_path", sa.String(), nullable=False),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_auto_import_records_fingerprint", "fingerprint", unique=True),
    sa.Index("ix_auto_import_records_id", "id"),
)

sa.Table(
    "defects",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("category", sa.String(), nullable=False),
    sa.Column("severity", sa.String()),
    sa.Column("note", sa.Text()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_defects_id", "id"),
    sa.Index("ix_defects_session_id", "session_id"),
)

sa.Table(
    "flight_entries",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("battery_id", sa.String()),
    sa.Column("start_pct", sa.Float()),
    sa.Column("end_pct", sa.Float()),
    sa.Column("duration_s", sa.Float()),
    sa.Column("notes", sa.Text()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_flight_entries_id", "id"),
    sa.Index("ix_flight_entries_session_id", "session_id"),
)

sa.Table(
    "flight_logs",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("filename", sa.String()),
    sa.Column("filepath", sa.String()),
    sa.Column("format", sa.String()),
    sa.Column("point_count", sa.Integer()),
    sa.Column("log_version", sa.Integer()),
    sa.Column("aircraft_name", sa.String()),
    sa.Column("aircraft_sn", sa.String()),
    sa.Column("encrypted", sa.Boolean()),
    sa.Column("uploaded_at", sa.DateTime()),
    sa.Index("ix_flight_logs_id", "id"),
    sa.Index("ix_flight_logs_session_id", "session_id"),
)

sa.Table(
    "images",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("filename", sa.String(), nullable=False),
    sa.Column("filepath", sa.String(), nullable=False),
    sa.Column("thumb_path", sa.String()),
    sa.Column("timestamp", sa.DateTime()),
    sa.Column("latitude", sa.Float()),
    sa.Column("longitude", sa.Float()),
    sa.Column("altitude_m", sa.Float()),
    sa.Column("original_latitude", sa.Float()),
    sa.Column("original_longitude", sa.Float()),
    sa.Column("original_altitude_m", sa.Float()),
    sa.Column("synced_latitude", sa.Float()),
    sa.Column("synced_longitude", sa.Float()),
    sa.Column("synced_altitude_m", sa.Float()),
    sa.Column("gps_source", sa.String()),
    sa.Column("yaw", sa.Float()),
    sa.Column("gimbal_pitch", sa.Float()),
    sa.Column("width", sa.Integer()),
    sa.Column("height", sa.Integer()),
    sa.Column("focal_length_mm", sa.Float()),
    sa.Column("camera_make", sa.String()),
    sa.Column("camera_model", sa.String()),
    sa.Column("lens_model", sa.String()),
    sa.Column("focal_length_35mm", sa.Float()),
    sa.Column("digital_zoom_ratio", sa.Float()),
    sa.Column("sharpness_score", sa.Float()),
    sa.Column("brightness_score", sa.Float()),
    sa.Column("flag", sa.String()),
    sa.Column("usable", sa.Boolean()),
    sa.Column("notes", sa.Text()),
    sa.Index("ix_images_id", "id"),
    sa.Index("ix_images_session_id", "session_id"),
)

sa.Table(
    "mission_plans",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("target_area_id", sa.Integer(), sa.ForeignKey("target_areas.id"), nullable=False),
    sa.Column("coverage_run_id", sa.Integer(), sa.ForeignKey("coverage_runs.id")),
    sa.Column("altitude_ft", sa.Float()),
    sa.Column("side_overlap_pct", sa.Float()),
    sa.Column("forward_overlap_pct", sa.Float()),
    sa.Column("lane_spacing_ft", sa.Float()),
    sa.Column("lane_count", sa.Integer()),
    sa.Column("total_distance_m", sa.Float()),
    sa.Column("batteries_estimated", sa.Float()),
    sa.Column("lanes_geojson", sa.Text()),
    sa.Column("kml_path", sa.String()),
    sa.Column("gpx_path", sa.String()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_mission_plans_id", "id"),
)

sa.Table(
    "reconstructions",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("parent_reconstruction_id", sa.Integer(), sa.ForeignKey("reconstructions.id")),
    sa.Column("status", sa.String()),
    sa.Column("preset", sa.String()),
    sa.Column("progress_pct", sa.Float()),
    sa.Column("step", sa.String()),
    sa.Column("frames_used", sa.Integer()),
    sa.Column("frames_registered", sa.Integer()),
    sa.Column("gaussian_count", sa.Integer()),
    sa.Column("psnr", sa.Float()),
    sa.Column("ssim", sa.Float()),
    sa.Column("colmap_dir", sa.String()),
    sa.Column("splat_path", sa.String()),
    sa.Column("splat_preview_path", sa.String()),
    sa.Column("splat_medium_path", sa.String()),
    sa.Column("thumb_path", sa.String()),
    sa.Column("pointcloud_path", sa.String()),
    sa.Column("mesh_glb_path", sa.String()),
    sa.Column("mesh_obj_path", sa.String()),
    sa.Column("mesh_mtl_path", sa.String()),
    sa.Column("mesh_status", sa.String()),
    sa.Column("mesh_error", sa.String()),
    sa.Column("flythrough_path", sa.String()),
    sa.Column("flythrough_status", sa.String()),
    sa.Column("flythrough_error", sa.String()),
    sa.Column("ortho_path", sa.String()),
    sa.Column("ortho_status", sa.String()),
    sa.Column("ortho_error", sa.String()),
    sa.Column("semantic_status", sa.String()),
    sa.Column("semantic_error", sa.String()),
    sa.Column("semantic_labels_path", sa.String()),
    sa.Column("geo_transform", sa.Text()),
    sa.Column("error_msg", sa.String()),
    sa.Column("started_at", sa.DateTime()),
    sa.Column("completed_at", sa.DateTime()),
    sa.Column("duration_s", sa.Float()),
    sa.Column("training_metrics", sa.Text()),
    sa.Column("effective_splat_settings", sa.Text()),
    sa.Column("coverage_gaps_path", sa.String()),
    sa.Column("source_session_ids", sa.Text()),
    sa.Index("ix_reconstructions_id", "id"),
    sa.Index("ix_reconstructions_parent_reconstruction_id", "parent_reconstruction_id"),
    sa.Index("ix_reconstructions_session_id", "session_id"),
)

sa.Table(
    "session_log_entries",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id")),
    sa.Column("timestamp", sa.DateTime()),
    sa.Column("event_type", sa.String()),
    sa.Column("coverage_pct", sa.Float()),
    sa.Column("photo_count", sa.Integer()),
    sa.Column("message", sa.Text()),
    sa.Index("ix_session_log_entries_id", "id"),
    sa.Index("ix_session_log_entries_session_id", "session_id"),
)

sa.Table(
    "annotations",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column(
        "reconstruction_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), nullable=False
    ),
    sa.Column("label", sa.String(), nullable=False),
    sa.Column("lat", sa.Float(), nullable=False),
    sa.Column("lon", sa.Float(), nullable=False),
    sa.Column("alt_m", sa.Float(), nullable=False),
    sa.Column("color", sa.String()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_annotations_id", "id"),
    sa.Index("ix_annotations_reconstruction_id", "reconstruction_id"),
)

sa.Table(
    "defect_images",
    _BASELINE,
    sa.Column("defect_id", sa.Integer(), sa.ForeignKey("defects.id"), primary_key=True),
    sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id"), primary_key=True),
)

sa.Table(
    "flight_log_points",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("flight_log_id", sa.Integer(), sa.ForeignKey("flight_logs.id"), nullable=False),
    sa.Column("timestamp", sa.DateTime()),
    sa.Column("latitude", sa.Float()),
    sa.Column("longitude", sa.Float()),
    sa.Column("altitude_m", sa.Float()),
    sa.Column("speed_ms", sa.Float()),
    sa.Column("heading", sa.Float()),
    sa.Column("roll", sa.Float()),
    sa.Column("pitch", sa.Float()),
    sa.Column("yaw", sa.Float()),
    sa.Column("gimbal_pitch", sa.Float()),
    sa.Column("gimbal_roll", sa.Float()),
    sa.Column("gimbal_yaw", sa.Float()),
    sa.Column("battery_voltage", sa.Float()),
    sa.Column("battery_charge_pct", sa.Float()),
    sa.Column("battery_temperature_c", sa.Float()),
    sa.Index("ix_flight_log_points_flight_log_id", "flight_log_id"),
    sa.Index("ix_flight_log_points_id", "id"),
)

sa.Table(
    "footprints",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id"), nullable=False),
    sa.Column("geom_wkt", sa.Text()),
    sa.Column("geom_geojson", sa.Text()),
    sa.Column("ground_width_m", sa.Float()),
    sa.Column("ground_height_m", sa.Float()),
    sa.Column("heading_estimated", sa.Boolean()),
    sa.Column("pitch_oblique", sa.Boolean()),
    sa.Index("ix_footprints_id", "id"),
    sa.Index("ix_footprints_image_id", "image_id"),
)

sa.Table(
    "measurements",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column(
        "reconstruction_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), nullable=False
    ),
    sa.Column("kind", sa.String(), nullable=False),
    sa.Column("points_json", sa.Text(), nullable=False),
    sa.Column("value", sa.Float()),
    sa.Column("unit", sa.String()),
    sa.Column("label", sa.String()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_measurements_id", "id"),
    sa.Index("ix_measurements_reconstruction_id", "reconstruction_id"),
)

sa.Table(
    "reconstruction_frames",
    _BASELINE,
    sa.Column(
        "reconstruction_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), primary_key=True
    ),
    sa.Column(
        "image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), primary_key=True
    ),
    sa.Column("colmap_error_px", sa.Float()),
)

sa.Table(
    "session_comparisons",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("session_a_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column("session_b_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
    sa.Column(
        "reconstruction_a_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), nullable=False
    ),
    sa.Column(
        "reconstruction_b_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), nullable=False
    ),
    sa.Column("status", sa.String()),
    sa.Column("diff_path", sa.String()),
    sa.Column("error_msg", sa.String()),
    sa.Column("created_at", sa.DateTime()),
    sa.Column("completed_at", sa.DateTime()),
    sa.Index("ix_session_comparisons_id", "id"),
)

sa.Table(
    "session_frame_selections",
    _BASELINE,
    sa.Column(
        "session_id",
        sa.Integer(),
        sa.ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), primary_key=True
    ),
)

sa.Table(
    "share_links",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column(
        "reconstruction_id", sa.Integer(), sa.ForeignKey("reconstructions.id"), nullable=False
    ),
    sa.Column("token_hash", sa.String(), nullable=False),
    sa.Column("expires_at", sa.DateTime(), nullable=False),
    sa.Column("password_hash", sa.Text()),
    sa.Column("revoked_at", sa.DateTime()),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_share_links_id", "id"),
    sa.Index("ix_share_links_reconstruction_id", "reconstruction_id"),
    sa.Index("ix_share_links_token_hash", "token_hash", unique=True),
)

sa.Table(
    "share_link_unlock_sessions",
    _BASELINE,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("share_link_id", sa.Integer(), sa.ForeignKey("share_links.id"), nullable=False),
    sa.Column("token_hash", sa.String(), nullable=False),
    sa.Column("expires_at", sa.DateTime(), nullable=False),
    sa.Column("created_at", sa.DateTime()),
    sa.Index("ix_share_link_unlock_sessions_id", "id"),
    sa.Index("ix_share_link_unlock_sessions_token_hash", "token_hash", unique=True),
)

# Columns that used to be added on the fly by the old _ensure_sqlite_schema
# shim. Kept here explicitly (rather than diffing against models.py) so this
# migration's behavior is stable even if the model definition changes later.
#
# Convention: keep this backfill limited to legacy columns that have no later
# Alembic revision owner. Columns introduced by a numbered revision belong only
# in that revision; the revision should stay idempotent for legacy DB upgrades.
_RECONSTRUCTIONS_SHIM_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "mesh_glb_path": sa.String(),
    "mesh_obj_path": sa.String(),
    "mesh_mtl_path": sa.String(),
    "mesh_status": sa.String(),
    "mesh_error": sa.String(),
    "flythrough_path": sa.String(),
    "flythrough_status": sa.String(),
    "flythrough_error": sa.String(),
}

_IMAGES_CALIBRATION_COLUMNS: dict[str, sa.types.TypeEngine] = {
    "camera_make": sa.String(),
    "camera_model": sa.String(),
    "lens_model": sa.String(),
    "focal_length_35mm": sa.Float(),
    "digital_zoom_ratio": sa.Float(),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Case 1: create any table that doesn't already exist yet (covers both
    # a fresh DB and partially-created ones).
    for table in _BASELINE.sorted_tables:
        if table.name not in existing_tables:
            table.create(bind=bind)

    # Case 2: backfill any columns missing from pre-existing legacy tables.
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()
    if "reconstructions" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("reconstructions")}
        for name, col_type in _RECONSTRUCTIONS_SHIM_COLUMNS.items():
            if name not in existing_columns:
                op.add_column("reconstructions", sa.Column(name, col_type))

    if "images" in table_names:
        existing_columns = {col["name"] for col in inspector.get_columns("images")}
        for name, col_type in _IMAGES_CALIBRATION_COLUMNS.items():
            if name not in existing_columns:
                op.add_column("images", sa.Column(name, col_type))
                existing_columns.add(name)


def downgrade() -> None:
    # This is the baseline revision for a hobby project with no production
    # migration history to preserve; downgrading below it is not supported.
    pass
