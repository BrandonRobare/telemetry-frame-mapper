"""Public response documentation for routes returning dictionaries.

Used only in responses metadata; payload serialization and validation are unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TrainingMetricPoint(BaseModel):
    iter: int
    psnr: float
    ssim: float


class CoverageGapCell(BaseModel):
    x: float
    y: float
    z: float
    size: float
    level: Literal["sparse", "thin", "very_sparse"]


class EffectiveSplatSettings(BaseModel):
    preset: str
    accelerator_kind: Literal["cuda", "metal", "cpu"]
    device: Literal["cuda", "mps", "cpu"]
    splat_backend: Literal["cuda_gsplat", "metal_msplat"] | None
    iterations: int
    max_gaussians: int
    # Stored settings from earlier runs may omit trainer-only fields.
    sh_degree: int = None
    downscale_factor: int = None
    refine_start_iter: int = None
    refine_stop_iter: int = None
    refine_every: int = None
    reset_every: int = None
    eval_every: int = None
    eval_views: int = None
    ssim_lambda: float = None
    init_opacity: float = None
    sh_warmup_every: int = None
    benchmark_heldout_split: bool = None
    benchmark_test_every: int = None
    background_color: tuple[float, float, float] | None = None


SemanticClassName = Literal["ground", "vegetation", "structure", "vehicle", "water", "other"]


class SemanticClassCounts(BaseModel):
    ground: int
    vegetation: int
    structure: int
    vehicle: int
    water: int
    other: int


class SemanticSummary(BaseModel):
    lod: Literal["full", "medium", "preview"]
    count: int
    class_counts: SemanticClassCounts
    unlabeled: int
    confidence_mean: float | None
    meta: dict[str, Any]


ReconstructionStatus = Literal[
    "pending",
    "running_colmap",
    "running_gsplat",
    "running_remote",
    "cancelling",
    "cancelled",
    "complete",
    "failed",
]


class Job(BaseModel):
    id: int
    type: Literal["reconstruction"]
    session_id: int
    source_session_ids: list[int] | None
    status: ReconstructionStatus
    preset: str
    progress_pct: float
    step: str
    frames_used: int
    started_at: str | None
    completed_at: str | None
    error_msg: str | None
    effective_splat_settings: EffectiveSplatSettings | None


class StorageSessionBreakdown(BaseModel):
    session_id: str
    bytes: int


class StorageStatsByType(BaseModel):
    imports: int
    processed: int
    exports: int
    data: int


class StorageStats(BaseModel):
    total_bytes: int
    by_type: StorageStatsByType
    by_session: list[StorageSessionBreakdown]


class BackupScheduleStatusResult(BaseModel):
    status: Literal["success", "failed", "configuration_error"]
    snapshot_id: str = None
    destination: str = None
    file_count: int = None
    manifest_sha256: str = None


class BackupScheduleStatus(BaseModel):
    enabled: bool
    target: str | None
    daily_at: str | None
    running: bool
    last_run: str | None
    next_run: str | None
    result: BackupScheduleStatusResult | None


class SystemAccelerator(BaseModel):
    kind: Literal["cuda", "metal", "cpu"]
    device: Literal["cuda", "mps", "cpu"]
    description: str
    splat_backend: Literal["cuda_gsplat", "metal_msplat"] | None
    splat_backend_available: bool


class SystemResources(BaseModel):
    cpu_pct: float
    ram_used_gb: float
    ram_total_gb: float
    disk_used_gb: float
    disk_total_gb: float
    disk_io_mbps: float | None
    gpu_pct: float | None
    vram_used_gb: float | None
    vram_total_gb: float | None
    gpu_name: str | None
    accelerator: SystemAccelerator
    colmap_capabilities: dict[str, Any]
    splat_transform_available: bool
    colmap_available: bool
    tools: list[SystemTool]
    workflows: list[WorkflowStatus]


class SystemTool(BaseModel):
    key: Literal[
        "ffmpeg", "exiftool", "colmap", "torch", "gsplat", "msplat", "sugar", "transformers"
    ]
    label: str
    available: bool
    path: str | None
    version: str | None
    install_commands: dict[str, str]
    install_hint: str | None
    error: str | None


class WorkflowStatus(BaseModel):
    key: str
    label: str
    available: bool
    missing: list[str]


class OrthoStatus(BaseModel):
    id: int
    ortho_status: Literal["pending", "running", "complete", "failed"] | None
    ortho_error: str | None
    ortho_path: str | None


class GeoTransform(BaseModel):
    scale: float
    rotation: tuple[
        tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
    ]
    translation: tuple[float, float, float]
    utm_zone: str
    utm_origin: tuple[float, float]
    rmse_m: float = None
    trimmed_point_count: int = None


class StorageFileItem(BaseModel):
    name: str
    path: str
    size_bytes: int
    modified: float


class StorageFileList(BaseModel):
    directory: str
    files: list[StorageFileItem]


class PolicyCandidate(BaseModel):
    path: str
    bytes: int
    reason: str
    action: str
    directory: bool


class PolicySummary(BaseModel):
    total_items: int
    total_bytes: int
    actions: dict[str, int]
    removed_items: int = None
    failed_items: int = None


class PolicyResultExecutedFailed(BaseModel):
    path: str
    reason: str


class PolicyResultExecuted(BaseModel):
    removed: list[str]
    failed: list[PolicyResultExecutedFailed]


class PolicyResult(BaseModel):
    mode: Literal["dry-run", "execute"]
    candidates: list[PolicyCandidate]
    summary: PolicySummary
    executed: PolicyResultExecuted = None


class SurveyReportSession(BaseModel):
    id: int
    name: str
    folder_path: str | None
    imported_at: str | None
    photo_count: int
    usable_count: int
    notes: str | None


class SurveyReportCamera(BaseModel):
    make: str | None
    model: str | None
    width: int | None
    height: int | None
    focal_length_mm: float | None


class SurveyReportFrameSummary(BaseModel):
    total: int
    usable: int
    quality_breakdown: dict[str, int]
    camera: SurveyReportCamera | None
    gps_present: int


class SurveyReportGps(BaseModel):
    missing_frames: int
    completeness_pct: float


class SurveyReportTimestamps(BaseModel):
    missing: int
    completeness_pct: float
    duplicate_groups: int
    gap_count: int


class SurveyReportOpticalQuality(BaseModel):
    blur_pct: float
    dark_pct: float
    bright_pct: float


class SurveyReportQualityAssessment(BaseModel):
    available: bool
    reason: str = None
    score: float | None = None
    safe_to_reconstruct: str | None = None
    recommended_action: str | None = None
    warnings: list[str] = None
    gps: SurveyReportGps = None
    timestamps: SurveyReportTimestamps = None
    optical_quality: SurveyReportOpticalQuality = None
    match_density: dict[str, Any] | None = None


class SurveyReportCoverage(BaseModel):
    available: bool
    footprint_count: int = None
    coverage_pct: float = None
    estimated_overlap_pct: float | None = None
    union_area: float = None
    summed_footprint_area: float = None
    warnings: list[str] = None


class SurveyReportReconstruction(BaseModel):
    id: int
    status: str
    preset: str
    frames_used: int
    frames_registered: int | None
    gaussian_count: int | None
    psnr: float | None
    ssim: float | None
    mesh_status: str | None
    flythrough_status: str | None
    started_at: str | None
    completed_at: str | None
    duration_s: float | None
    artifacts: dict[str, str]
    training_metrics: dict[str, list[TrainingMetricPoint]]


class SurveyReportAnnotation(BaseModel):
    id: int
    reconstruction_id: int
    label: str
    lat: float
    lon: float
    alt_m: float
    color: str
    created_at: str | None


class SurveyReport(BaseModel):
    report_type: str
    version: str
    generated_at: str
    session: SurveyReportSession
    frame_summary: SurveyReportFrameSummary
    quality_assessment: SurveyReportQualityAssessment
    coverage: SurveyReportCoverage
    reconstructions: list[SurveyReportReconstruction]
    annotations: list[SurveyReportAnnotation]
    html: str


class ComparisonCell(BaseModel):
    x: float
    y: float
    z: float
    size: float
    type: Literal["new", "removed"]


class ComparisonDiffComparison(BaseModel):
    session_a_id: int
    session_b_id: int
    reconstruction_a_id: int
    reconstruction_b_id: int


class ComparisonDiffSummary(BaseModel):
    a_cells: int
    b_cells: int
    new_count: int
    removed_count: int


class ComparisonDiff(BaseModel):
    comparison: ComparisonDiffComparison
    voxel_size_m: float
    utm_zone: str | None
    summary: ComparisonDiffSummary
    new: list[ComparisonCell]
    removed: list[ComparisonCell]


class QualityScorecardFrameCounts(BaseModel):
    frames_used: int
    frames_registered: int
    registration_completeness_pct: float


class QualityScorecardDensity(BaseModel):
    gaussian_count: int | None


class QualityScorecardReprojectionError(BaseModel):
    mean_px: float | None
    std_px: float | None
    min_px: float | None
    max_px: float | None
    frame_count_with_data: int


class MetricTrend(BaseModel):
    start: float
    end: float
    delta: float


class QualityScorecardQuality(BaseModel):
    psnr_final: float | None
    ssim_final: float | None
    training_metric_points: int
    psnr_trend: MetricTrend = None
    ssim_trend: MetricTrend = None


class QualityScorecardCoverageGaps(BaseModel):
    total_gaps: int
    by_level: dict[str, int]
    voxel_size_m: float = None


class QualityScorecard(BaseModel):
    reconstruction_id: int
    frame_counts: QualityScorecardFrameCounts
    density: QualityScorecardDensity
    reprojection_error: QualityScorecardReprojectionError
    quality: QualityScorecardQuality
    coverage_gaps: QualityScorecardCoverageGaps | None


class GcpResidual(BaseModel):
    label: str
    dx_m: float
    dy_m: float
    dz_m: float
    distance_3d_m: float


class GcpAccuracyReportRmse(BaseModel):
    x_m: float | None
    y_m: float | None
    z_m: float | None
    three_d_m: float | None = Field(alias="3d_m")


class GcpAccuracyReport(BaseModel):
    geo_transform: GeoTransform
    point_count: int
    rmse: GcpAccuracyReportRmse
    residuals: list[GcpResidual]


class CheckpointResult(BaseModel):
    label: str
    distance_m: float
    nearest_surface_point: str


class CheckpointValidationReportSummary(BaseModel):
    min_m: float | None
    max_m: float | None
    mean_m: float | None
    rmse_m: float | None


class CheckpointValidationReport(BaseModel):
    available: Literal[True]
    source: Literal["mesh", "splat", "pointcloud"]
    frame: dict[str, str]
    point_count: int
    surface_point_count: int
    summary: CheckpointValidationReportSummary
    checkpoints: list[CheckpointResult]


class PreflightLighting(BaseModel):
    sample_count: int
    p10_p90_spread: float | None
    threshold: float
    inconsistent: bool


class CreatedShareLink(BaseModel):
    share_token: str
    share_link_id: int
    reconstruction_id: int
    session_id: int
    expires_at: str
    password_protected: bool


class ShareLinkState(BaseModel):
    id: int
    reconstruction_id: int
    expires_at: str
    password_protected: bool
    revoked_at: str | None
    created_at: str


class GeneralSettingsRead(BaseModel):
    default_basemap: str
    target_crs: str
    imports_dir: str
    processed_dir: str
    exports_dir: str
    data_dir: str
    basemap_providers: list[dict[str, Any]]


class MissionSettingsRead(BaseModel):
    altitude_ft: float
    fov_horizontal_deg: float
    fov_vertical_deg: float
    image_width_px: int
    image_height_px: int
    desired_side_overlap: float
    desired_forward_overlap: float
    lane_spacing_ft: float
    default_video_fps: float
    battery_range_m: float
    mission_buffer_pct: float
    flight_log_match_tolerance_sec: float


class IngestSettingsRead(BaseModel):
    # YAML merges retain operator keys beyond the recognized settings.
    model_config = {"extra": "allow"}

    thumbnail_size_px: int
    thumbnail_jpeg_quality: int
    accepted_extensions: list[str]
    blur_threshold: float
    dark_threshold: float
    bright_threshold: float
    filter_zero_gps: bool


class PresetConfigRead(BaseModel):
    model_config = {"extra": "allow"}

    iterations: int
    max_gaussians: int
    sh_degree: int
    downscale_factor: int


class ReconstructionSettingsRead(BaseModel):
    model_config = {"extra": "allow"}

    default_preset: str
    colmap_threads: int
    sift_max_features: int
    matcher: str
    mapper: str
    spatial_matcher_min_images: int
    camera_model: str
    single_camera: bool
    dense_rerun: dict[str, Any]
    camera_profiles: list[dict[str, Any]]
    presets: dict[str, PresetConfigRead]


class RenderSettingsRead(BaseModel):
    model_config = {"extra": "allow"}

    flythrough_fps: int
    flythrough_width: int
    flythrough_height: int
    thumbnail_size_px: int
    thumbnail_quality: int
    lod_preview_ratio: float
    lod_medium_ratio: float


class AppSettings(BaseModel):
    general: GeneralSettingsRead
    mission: MissionSettingsRead
    ingest: IngestSettingsRead
    reconstruction: ReconstructionSettingsRead
    render: RenderSettingsRead


class SessionProgress(BaseModel):
    processed: int
    total: int
    skipped: int = None
    status: Literal["pending", "running", "done", "error", "unknown"]
    error: str = None


class ShareViewerArtifacts(BaseModel):
    pointcloud: str
    mesh_glb: str | None
    mesh_obj: str | None


class ShareViewerPayload(BaseModel):
    reconstruction_id: int
    session_id: int
    status: str
    frames_used: int
    frames_registered: int | None
    gaussian_count: int | None
    psnr: float | None
    ssim: float | None
    artifacts: ShareViewerArtifacts
    legacy_token_required: bool
    generated_at: float
