from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from backend.db.database import Base


class UtcDateTime(TypeDecorator):
    """DateTime that always reads back as timezone-aware UTC.

    Every timestamp here is written as ``datetime.now(UTC)``, but SQLite's
    DATETIME drops the tzinfo, so values came back naive and FastAPI serialised them
    with no offset (``2026-07-28T13:19:53.466047``). A client cannot tell that is
    UTC — JavaScript parses a bare timestamp as *local* time, which placed running
    jobs hours in the future and rendered a negative elapsed counter.

    Storage format is unchanged (naive UTC on disk), so this needs no migration.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # Session-bundle restore hands back ISO strings straight from JSON. SQLite
        # accepted those verbatim before this type existed, leaving strings sitting
        # in DATETIME columns; parse them so every row holds a real timestamp.
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    folder_path = Column(String)
    import_mode = Column(String, default="full")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    imported_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    photo_count = Column(Integer, default=0)
    usable_count = Column(Integer, default=0)
    notes = Column(Text)
    tags = Column(Text)  # JSON list of short strings, e.g. '["roof", "solar"]'
    images = relationship("Image", back_populates="session", cascade="all, delete-orphan")
    flight_logs = relationship("FlightLog", back_populates="session", cascade="all, delete-orphan")
    flight_entries = relationship(
        "FlightEntry", back_populates="session", cascade="all, delete-orphan"
    )
    log_entries = relationship(
        "SessionLogEntry", back_populates="session", cascade="all, delete-orphan"
    )
    reconstructions = relationship(
        "Reconstruction", back_populates="session", cascade="all, delete-orphan"
    )
    comparisons_as_a = relationship(
        "SessionComparison",
        foreign_keys="SessionComparison.session_a_id",
        cascade="all, delete-orphan",
    )
    comparisons_as_b = relationship(
        "SessionComparison",
        foreign_keys="SessionComparison.session_b_id",
        cascade="all, delete-orphan",
    )
    frame_selections = relationship(
        "SessionFrameSelection", cascade="all, delete-orphan", passive_deletes=True
    )
    defects = relationship("Defect", back_populates="session", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="sessions")


class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    thumb_path = Column(String)
    timestamp = Column(UtcDateTime)
    latitude = Column(Float)
    longitude = Column(Float)
    altitude_m = Column(Float)
    original_latitude = Column(Float)
    original_longitude = Column(Float)
    original_altitude_m = Column(Float)
    synced_latitude = Column(Float)
    synced_longitude = Column(Float)
    synced_altitude_m = Column(Float)
    gps_source = Column(String, default="none")
    yaw = Column(Float)
    gimbal_pitch = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    focal_length_mm = Column(Float)
    camera_make = Column(String)
    camera_model = Column(String)
    lens_model = Column(String)
    focal_length_35mm = Column(Float)
    digital_zoom_ratio = Column(Float)
    sharpness_score = Column(Float)
    brightness_score = Column(Float)
    flag = Column(String, default="good")
    usable = Column(Boolean, default=True)
    notes = Column(Text)
    session = relationship("Session", back_populates="images")
    footprint = relationship(
        "Footprint", back_populates="image", uselist=False, cascade="all, delete-orphan"
    )


class Footprint(Base):
    __tablename__ = "footprints"
    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    geom_wkt = Column(Text)
    geom_geojson = Column(Text)
    ground_width_m = Column(Float)
    ground_height_m = Column(Float)
    heading_estimated = Column(Boolean, default=True)
    pitch_oblique = Column(Boolean, default=False)
    image = relationship("Image", back_populates="footprint")


class FlightLog(Base):
    __tablename__ = "flight_logs"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    filename = Column(String)
    filepath = Column(String)
    format = Column(String)
    point_count = Column(Integer, default=0)
    log_version = Column(Integer)
    aircraft_name = Column(String)
    aircraft_sn = Column(String)
    encrypted = Column(Boolean, default=False)
    uploaded_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    session = relationship("Session", back_populates="flight_logs")
    points = relationship(
        "FlightLogPoint", back_populates="flight_log", cascade="all, delete-orphan"
    )


class FlightLogPoint(Base):
    __tablename__ = "flight_log_points"
    id = Column(Integer, primary_key=True, index=True)
    flight_log_id = Column(Integer, ForeignKey("flight_logs.id"), nullable=False)
    timestamp = Column(UtcDateTime)
    latitude = Column(Float)
    longitude = Column(Float)
    altitude_m = Column(Float)
    speed_ms = Column(Float)
    heading = Column(Float)
    roll = Column(Float)
    pitch = Column(Float)
    yaw = Column(Float)
    gimbal_pitch = Column(Float)
    gimbal_roll = Column(Float)
    gimbal_yaw = Column(Float)
    battery_voltage = Column(Float)
    battery_charge_pct = Column(Float)
    battery_temperature_c = Column(Float)
    flight_log = relationship("FlightLog", back_populates="points")


class FlightEntry(Base):
    """Operator-recorded battery/flight metadata for a session (field records)."""
    __tablename__ = "flight_entries"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    battery_id = Column(String)
    start_pct = Column(Float)
    end_pct = Column(Float)
    duration_s = Column(Float)
    notes = Column(Text)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    session = relationship("Session", back_populates="flight_entries")


class TargetArea(Base):
    __tablename__ = "target_areas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    geom_geojson = Column(Text)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    notes = Column(Text)
    coverage_runs = relationship(
        "CoverageRun", back_populates="target_area", cascade="all, delete-orphan"
    )
    mission_plans = relationship(
        "MissionPlan", back_populates="target_area", cascade="all, delete-orphan"
    )


class CoverageRun(Base):
    __tablename__ = "coverage_runs"
    id = Column(Integer, primary_key=True, index=True)
    target_area_id = Column(Integer, ForeignKey("target_areas.id"), nullable=False)
    session_ids = Column(Text)
    total_area_m2 = Column(Float)
    covered_area_m2 = Column(Float)
    coverage_pct = Column(Float)
    gap_geojson = Column(Text)
    overlap_geojson = Column(Text)
    run_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    target_area = relationship("TargetArea", back_populates="coverage_runs")
    mission_plans = relationship("MissionPlan", back_populates="coverage_run")


class MissionPlan(Base):
    __tablename__ = "mission_plans"
    id = Column(Integer, primary_key=True, index=True)
    target_area_id = Column(Integer, ForeignKey("target_areas.id"), nullable=False)
    coverage_run_id = Column(Integer, ForeignKey("coverage_runs.id"), nullable=True)
    altitude_ft = Column(Float)
    side_overlap_pct = Column(Float)
    forward_overlap_pct = Column(Float)
    lane_spacing_ft = Column(Float)
    lane_count = Column(Integer)
    total_distance_m = Column(Float)
    batteries_estimated = Column(Float)
    lanes_geojson = Column(Text)
    kml_path = Column(String)
    gpx_path = Column(String)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    target_area = relationship("TargetArea", back_populates="mission_plans")
    coverage_run = relationship("CoverageRun", back_populates="mission_plans")


class SessionLogEntry(Base):
    __tablename__ = "session_log_entries"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    timestamp = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    event_type = Column(String)
    coverage_pct = Column(Float)
    photo_count = Column(Integer)
    message = Column(Text)
    session = relationship("Session", back_populates="log_entries")


class Reconstruction(Base):
    __tablename__ = "reconstructions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    parent_reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=True)
    status = Column(String, default="pending")
    preset = Column(String, default="quick")
    progress_pct = Column(Float, default=0.0)
    step = Column(String, default="")
    frames_used = Column(Integer, default=0)
    frames_registered = Column(Integer)
    gaussian_count = Column(Integer)
    psnr = Column(Float)
    ssim = Column(Float)
    colmap_dir = Column(String)
    splat_path = Column(String)
    splat_preview_path = Column(String)
    splat_medium_path = Column(String)
    thumb_path = Column(String)
    pointcloud_path = Column(String)
    mesh_glb_path = Column(String)
    mesh_obj_path = Column(String)
    mesh_mtl_path = Column(String)
    mesh_status = Column(String)
    mesh_error = Column(String)
    flythrough_path = Column(String)
    flythrough_status = Column(String)
    flythrough_error = Column(String)
    ortho_path = Column(String)
    ortho_status = Column(String)
    ortho_error = Column(String)
    semantic_status = Column(String)
    semantic_error = Column(String)
    semantic_labels_path = Column(String)
    geo_transform = Column(Text)
    error_msg = Column(String)
    started_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(UtcDateTime)
    duration_s = Column(Float)
    training_metrics = Column(Text)       # JSON: [{iter, psnr, ssim}, ...]
    coverage_gaps_path = Column(String)   # path to cached coverage_gaps.json
    # JSON list of source session IDs for multi-session reconstructions
    source_session_ids = Column(Text)
    session = relationship("Session", back_populates="reconstructions")
    parent = relationship("Reconstruction", remote_side=[id], back_populates="children")
    children = relationship("Reconstruction", back_populates="parent")
    frames = relationship(
        "ReconstructionFrame", back_populates="reconstruction", cascade="all, delete-orphan"
    )
    annotations = relationship(
        "Annotation", back_populates="reconstruction", cascade="all, delete-orphan"
    )
    measurements = relationship(
        "Measurement", back_populates="reconstruction", cascade="all, delete-orphan"
    )
    share_links = relationship(
        "ShareLink", back_populates="reconstruction", cascade="all, delete-orphan"
    )


class ShareLink(Base):
    """A revocable, opaque public link. Raw tokens are never persisted."""

    __tablename__ = "share_links"
    id = Column(Integer, primary_key=True, index=True)
    reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(UtcDateTime, nullable=False)
    password_hash = Column(Text)
    revoked_at = Column(UtcDateTime)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    reconstruction = relationship("Reconstruction", back_populates="share_links")
    unlock_sessions = relationship(
        "ShareLinkUnlockSession", back_populates="share_link", cascade="all, delete-orphan"
    )


class ShareLinkUnlockSession(Base):
    """One server-issued, cookie-backed unlock session for a protected share link."""

    __tablename__ = "share_link_unlock_sessions"
    id = Column(Integer, primary_key=True, index=True)
    share_link_id = Column(Integer, ForeignKey("share_links.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(UtcDateTime, nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    share_link = relationship("ShareLink", back_populates="unlock_sessions")


class ReconstructionFrame(Base):
    __tablename__ = "reconstruction_frames"
    reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), primary_key=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    colmap_error_px = Column(Float)  # null = frame not registered by COLMAP
    reconstruction = relationship("Reconstruction", back_populates="frames")
    image = relationship("Image")


class Annotation(Base):
    __tablename__ = "annotations"
    id = Column(Integer, primary_key=True, index=True)
    reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=False)
    label = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    alt_m = Column(Float, nullable=False)
    color = Column(String, default="#ff6b35")
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    reconstruction = relationship("Reconstruction", back_populates="annotations")


class Measurement(Base):
    """A viewer measurement (distance/area/point) persisted for a reconstruction.

    ``points_json`` mirrors the shape used by the splat viewer's ephemeral
    measurement state (frontend `measurementMath.ts` / `SplatViewerTab.tsx`
    `MeasurePoint`): a JSON list of ``{x, y, z, lat, lon, alt}`` objects, world
    coords plus optional GPS. ``value``/``unit`` hold the client-computed result
    (e.g. 111.0 / "m" for a distance, or an area in "m2").
    """
    __tablename__ = "measurements"
    id = Column(Integer, primary_key=True, index=True)
    reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=False)
    kind = Column(String, nullable=False)  # "distance" | "area" | "point"
    points_json = Column(Text, nullable=False)
    value = Column(Float)
    unit = Column(String)
    label = Column(String)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    reconstruction = relationship("Reconstruction", back_populates="measurements")


class Defect(Base):
    """Operator-flagged defect (crack, corrosion, etc.) linked to one or more source photos.

    Scoped to a session rather than a reconstruction so defects can be flagged during photo
    review, before any reconstruction has run. The linked images carry the GPS coordinates.
    """
    __tablename__ = "defects"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    category = Column(String, nullable=False)
    severity = Column(String)
    note = Column(Text)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    session = relationship("Session", back_populates="defects")
    image_links = relationship(
        "DefectImage", back_populates="defect", cascade="all, delete-orphan"
    )


class DefectImage(Base):
    """Many-to-many link between a Defect and the source Image(s) it was flagged from."""
    __tablename__ = "defect_images"
    defect_id = Column(Integer, ForeignKey("defects.id"), primary_key=True)
    image_id = Column(Integer, ForeignKey("images.id"), primary_key=True)
    defect = relationship("Defect", back_populates="image_links")
    image = relationship("Image")


class SessionFrameSelection(Base):
    __tablename__ = "session_frame_selections"
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)


class SessionComparison(Base):
    __tablename__ = "session_comparisons"
    id = Column(Integer, primary_key=True, index=True)
    session_a_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    session_b_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    reconstruction_a_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=False)
    reconstruction_b_id = Column(Integer, ForeignKey("reconstructions.id"), nullable=False)
    status = Column(String, default="pending")
    diff_path = Column(String)
    error_msg = Column(String)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(UtcDateTime)


class JobQueueEntry(Base):
    """Persistent job queue for resource-heavy async work (reconstruction, mesh, flythrough,
    comparison).  Jobs survive API restarts and are dispatched by a background worker that
    enforces GPU and concurrency caps.

    Each entry references a single target entity (Reconstruction, SessionComparison) via
    target_id; the job_type column discriminates so the worker knows which handler to call.
    """
    __tablename__ = "job_queue"
    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    priority = Column(Integer, default=0)
    payload_json = Column(Text)
    error_msg = Column(String)
    attempt = Column(Integer, default=0)
    max_attempts = Column(Integer, default=1)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
    started_at = Column(UtcDateTime)
    completed_at = Column(UtcDateTime)


class AutoImportRecord(Base):
    """A claimed watch-folder import.  The unique manifest fingerprint survives restarts."""

    __tablename__ = "auto_import_records"
    id = Column(Integer, primary_key=True, index=True)
    fingerprint = Column(String, nullable=False, unique=True, index=True)
    source_path = Column(String, nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(UTC))
