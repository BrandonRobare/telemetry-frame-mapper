from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.db.database import Base


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    folder_path = Column(String)
    import_mode = Column(String, default="full")
    imported_at = Column(DateTime, default=datetime.utcnow)
    photo_count = Column(Integer, default=0)
    usable_count = Column(Integer, default=0)
    notes = Column(Text)
    images = relationship("Image", back_populates="session", cascade="all, delete-orphan")
    flight_logs = relationship("FlightLog", back_populates="session", cascade="all, delete-orphan")
    log_entries = relationship(
        "SessionLogEntry", back_populates="session", cascade="all, delete-orphan"
    )
    reconstructions = relationship(
        "Reconstruction", back_populates="session", cascade="all, delete-orphan"
    )
    frame_selections = relationship(
        "SessionFrameSelection", cascade="all, delete-orphan", passive_deletes=True
    )


class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    thumb_path = Column(String)
    timestamp = Column(DateTime)
    latitude = Column(Float)
    longitude = Column(Float)
    altitude_m = Column(Float)
    gps_source = Column(String, default="none")
    yaw = Column(Float)
    gimbal_pitch = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    focal_length_mm = Column(Float)
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
    image = relationship("Image", back_populates="footprint")


class FlightLog(Base):
    __tablename__ = "flight_logs"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    filename = Column(String)
    filepath = Column(String)
    format = Column(String)
    point_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="flight_logs")
    points = relationship(
        "FlightLogPoint", back_populates="flight_log", cascade="all, delete-orphan"
    )


class FlightLogPoint(Base):
    __tablename__ = "flight_log_points"
    id = Column(Integer, primary_key=True, index=True)
    flight_log_id = Column(Integer, ForeignKey("flight_logs.id"), nullable=False)
    timestamp = Column(DateTime)
    latitude = Column(Float)
    longitude = Column(Float)
    altitude_m = Column(Float)
    speed_ms = Column(Float)
    heading = Column(Float)
    flight_log = relationship("FlightLog", back_populates="points")


class TargetArea(Base):
    __tablename__ = "target_areas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    geom_geojson = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    run_at = Column(DateTime, default=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    target_area = relationship("TargetArea", back_populates="mission_plans")
    coverage_run = relationship("CoverageRun", back_populates="mission_plans")


class SessionLogEntry(Base):
    __tablename__ = "session_log_entries"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)
    coverage_pct = Column(Float)
    photo_count = Column(Integer)
    message = Column(Text)
    session = relationship("Session", back_populates="log_entries")


class Reconstruction(Base):
    __tablename__ = "reconstructions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
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
    geo_transform = Column(Text)
    error_msg = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    duration_s = Column(Float)
    training_metrics = Column(Text)       # JSON: [{iter, psnr, ssim}, ...]
    coverage_gaps_path = Column(String)   # path to cached coverage_gaps.json
    session = relationship("Session", back_populates="reconstructions")
    frames = relationship(
        "ReconstructionFrame", back_populates="reconstruction", cascade="all, delete-orphan"
    )


class ReconstructionFrame(Base):
    __tablename__ = "reconstruction_frames"
    reconstruction_id = Column(Integer, ForeignKey("reconstructions.id"), primary_key=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    colmap_error_px = Column(Float)  # null = frame not registered by COLMAP
    reconstruction = relationship("Reconstruction", back_populates="frames")
    image = relationship("Image")


class SessionFrameSelection(Base):
    __tablename__ = "session_frame_selections"
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)
    image_id = Column(Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
