export interface Session {
  id: number;
  name: string;
  folder_path: string;
  import_mode: string;
  imported_at: string;
  photo_count: number;
  usable_count: number;
  notes: string | null;
}

export interface Image {
  id: number;
  session_id: number;
  filename: string;
  filepath: string;
  thumb_path: string | null;
  timestamp: string | null;
  latitude: number | null;
  longitude: number | null;
  altitude_m: number | null;
  original_latitude: number | null;
  original_longitude: number | null;
  original_altitude_m: number | null;
  synced_latitude: number | null;
  synced_longitude: number | null;
  synced_altitude_m: number | null;
  gps_source: string;
  yaw: number | null;
  gimbal_pitch: number | null;
  width: number | null;
  height: number | null;
  focal_length_mm: number | null;
  sharpness_score: number | null;
  brightness_score: number | null;
  colmap_error_px: number | null;
  flag: "good" | "blurry" | "dark" | "bright" | "no_gps";
  usable: boolean;
  notes: string | null;
}

export interface Footprint {
  id: number;
  image_id: number;
  geom_wkt: string;
  geom_geojson: string;
  ground_width_m: number;
  ground_height_m: number;
  heading_estimated: boolean;
}

export interface CoverageResult {
  id: number;
  target_area_id: number | null;
  session_ids: string;
  total_area_m2: number | null;
  covered_area_m2: number | null;
  coverage_pct: number | null;
  gap_geojson: string | null;
  overlap_geojson: string | null;
  run_at: string;
}

export interface TrainingMetricPoint {
  iter: number;
  psnr: number;
  ssim: number;
}

export interface CoverageGapCell {
  x: number;
  y: number;
  z: number;
  size: number;
  level: "sparse" | "thin" | "very_sparse";
}

export interface Reconstruction {
  id: number;
  session_id: number;
  status: "pending" | "running_colmap" | "running_gsplat" | "cancelling" | "cancelled" | "complete" | "failed";
  preset: "quick" | "full";
  progress_pct: number;
  step: string;
  frames_used: number;
  frames_registered: number | null;
  gaussian_count: number | null;
  psnr: number | null;
  ssim: number | null;
  training_metrics: TrainingMetricPoint[] | null;
  error_msg: string | null;
  geo_transform: string | null;
  splat_path: string | null;
  pointcloud_path: string | null;
  mesh_glb_path: string | null;
  mesh_obj_path: string | null;
  mesh_mtl_path: string | null;
  mesh_status: "pending" | "running" | "complete" | "failed" | null;
  mesh_error: string | null;
  flythrough_path: string | null;
  flythrough_status: "pending" | "running" | "complete" | "failed" | null;
  flythrough_error: string | null;
  semantic_status: "pending" | "running" | "complete" | "failed" | null;
  semantic_error: string | null;
  semantic_labels_path: string | null;
  coverage_gaps_path: string | null;
}

export interface MeshStatus {
  id: number
  mesh_status: "pending" | "running" | "complete" | "failed" | null
  mesh_error: string | null
  mesh_glb_path: string | null
  mesh_obj_path: string | null
  mesh_mtl_path: string | null
}

export interface FlythroughStatus {
  id: number
  flythrough_status: "pending" | "running" | "complete" | "failed" | null
  flythrough_error: string | null
  flythrough_path: string | null
}

export type SemanticClassName = 'ground' | 'vegetation' | 'structure' | 'vehicle' | 'water' | 'other'

export interface SemanticStatus {
  id: number
  semantic_status: 'pending' | 'running' | 'complete' | 'failed' | null
  semantic_error: string | null
  semantic_labels_path: string | null
}

export interface SemanticSummary {
  lod: 'full' | 'medium' | 'preview'
  count: number
  class_counts: Record<SemanticClassName, number>
  unlabeled: number
  confidence_mean: number | null
  meta: Record<string, unknown>
}

export const SEMANTIC_CLASS_COLORS: Record<SemanticClassName, string> = {
  ground: '#8a7a5c',
  vegetation: '#4F6349',
  structure: '#9A5E32',
  vehicle: '#3b82f6',
  water: '#38bdf8',
  other: '#9ca3af',
}

export interface HistogramBin {
  min: number;
  max: number;
  count: number;
}

export interface PreflightQualityReport {
  session_id: number;
  total_frames: number;
  usable_frames: number;
  gps: {
    missing: number;
    completeness_pct: number;
  };
  timestamps: {
    missing: number;
    completeness_pct: number;
    duplicate_groups: number;
    duplicate_frames: number;
    gap_count: number;
    max_gap_s: number;
    typical_gap_s: number | null;
    gap_threshold_s: number | null;
  };
  quality: {
    blur_threshold: number;
    dark_threshold: number;
    bright_threshold: number;
    blur_count: number;
    dark_count: number;
    bright_count: number;
    blur_pct: number;
    dark_pct: number;
    bright_pct: number;
    flag_counts: Record<string, number>;
    sharpness_histogram: HistogramBin[];
    brightness_histogram: HistogramBin[];
  };
  coverage: {
    footprint_count: number;
    footprint_coverage_pct: number;
    estimated_overlap_pct: number | null;
    union_area: number;
    summed_footprint_area: number;
    warnings: string[];
  };
  warnings: string[];
  safe_to_reconstruct: "yes" | "caution" | "no";
  score: number;
  recommended_action: string;
}

export interface QuickReport {
  session_id: number;
  total_frames: number;
  usable_frames: number;
  score: number;
  safe_to_reconstruct: "yes" | "caution" | "no";
  recommended_action: string;
  warnings: string[];
  gps_completeness_pct: number;
  timestamp_completeness_pct: number;
  blur_pct: number;
  exposure_issue_pct: number;
  estimated_overlap_pct: number | null;
  match_density_weak_ratio: number | null;
  match_density_avg_matches: number | null;
}

export interface Job {
  id: number;
  type: "reconstruction";
  session_id: number;
  source_session_ids: number[] | null;
  status: "pending" | "running_colmap" | "running_gsplat" | "cancelling" | "cancelled" | "complete" | "failed";
  preset: string;
  progress_pct: number;
  step: string;
  frames_used: number;
  started_at: string | null;
  completed_at: string | null;
  error_msg: string | null;
}

export interface StorageSessionBreakdown {
  session_id: string;
  bytes: number;
}

export interface StorageStats {
  total_bytes: number;
  by_type: {
    imports: number;
    processed: number;
    exports: number;
    data: number;
  };
  by_session: StorageSessionBreakdown[];
}

export interface SystemResources {
  cpu_pct: number
  ram_used_gb: number
  ram_total_gb: number
  disk_used_gb: number
  disk_total_gb: number
  disk_io_mbps: number | null
  gpu_pct: number | null
  vram_used_gb: number | null
  vram_total_gb: number | null
  gpu_name: string | null
  gpu_available: boolean
  colmap_available: boolean
  gsplat_available: boolean
  tools: SystemTool[]
  workflows: WorkflowStatus[]
}

export interface SystemTool {
  key: 'ffmpeg' | 'exiftool' | 'colmap' | 'torch' | 'gsplat' | 'sugar'
  label: string
  available: boolean
  path: string | null
  version: string | null
  cuda_available?: boolean
  install_commands: Record<string, string>
  error: string | null
}

export interface WorkflowStatus {
  key: string
  label: string
  available: boolean
  missing: string[]
}

export interface OrthoStatus {
  id: number
  ortho_status: "pending" | "running" | "complete" | "failed" | null
  ortho_error: string | null
  ortho_path: string | null
}

export interface GeoTransform {
  scale: number
  rotation: [[number, number, number], [number, number, number], [number, number, number]]
  translation: [number, number, number]
  utm_zone: string
  utm_origin: [number, number]
}

export interface StorageFileItem {
  name: string
  path: string
  size_bytes: number
  modified: number
}

export interface StorageFileList {
  directory: string
  files: StorageFileItem[]
}

export interface PolicyCandidate {
  path: string
  bytes: number
  reason: string
  action: string
  directory: boolean
}

export interface PolicySummary {
  total_items: number
  total_bytes: number
  actions: Record<string, number>
  removed_items?: number
  failed_items?: number
}

export interface PolicyResult {
  mode: "dry-run" | "execute"
  candidates: PolicyCandidate[]
  summary: PolicySummary
  executed?: {
    removed: string[]
    failed: { path: string; reason: string }[]
  }
}

export interface SurveyReport {
  report_type: string
  version: string
  generated_at: string
  session: {
    id: number
    name: string
    folder_path: string
    imported_at: string | null
    photo_count: number
    usable_count: number
    notes: string | null
  }
  frame_summary: {
    total: number
    usable: number
    quality_breakdown: Record<string, number>
    camera: Record<string, unknown> | null
    gps_present: number
  }
  quality_assessment: {
    available: boolean
    reason?: string
    score?: number
    safe_to_reconstruct?: string
    recommended_action?: string
    warnings?: string[]
  }
  coverage: { available: boolean }
  reconstructions: unknown[]
  annotations: unknown[]
  html: string
}

export interface Annotation {
  id: number
  reconstruction_id: number
  label: string
  lat: number
  lon: number
  alt_m: number
  color: string
  created_at: string
}

export interface SessionComparison {
  id: number
  session_a_id: number
  session_b_id: number
  reconstruction_a_id: number
  reconstruction_b_id: number
  status: "pending" | "running" | "complete" | "failed"
  diff_path: string | null
  error_msg: string | null
  created_at: string
  completed_at: string | null
}

export interface ComparisonCell {
  x: number
  y: number
  z: number
  size: number
  type: "new" | "removed"
}

export interface ComparisonDiff {
  comparison: {
    session_a_id: number
    session_b_id: number
    reconstruction_a_id: number
    reconstruction_b_id: number
  }
  voxel_size_m: number
  utm_zone: string | null
  summary: {
    a_cells: number
    b_cells: number
    new_count: number
    removed_count: number
  }
  new: ComparisonCell[]
  removed: ComparisonCell[]
}

// ---- Quality reports (issues #287, #292, #294) ----

export interface QualityScorecard {
  reconstruction_id: number
  frame_counts: {
    frames_used: number
    frames_registered: number
    registration_completeness_pct: number
  }
  density: {
    gaussian_count: number | null
  }
  reprojection_error: {
    mean_px: number | null
    std_px: number | null
    min_px: number | null
    max_px: number | null
    frame_count_with_data: number
  }
  quality: {
    psnr_final: number | null
    ssim_final: number | null
    training_metric_points: number
    psnr_trend?: {
      start: number
      end: number
      delta: number
    }
    ssim_trend?: {
      start: number
      end: number
      delta: number
    }
  }
  coverage_gaps: {
    total_gaps: number
    by_level: Record<string, number>
    voxel_size_m?: number
  } | null
}

export interface GcpResidual {
  label: string
  dx_m: number
  dy_m: number
  dz_m: number
  distance_3d_m: number
}

export interface GcpAccuracyPoint {
  label?: string
  x: number
  y: number
  z: number
  reconstructed_x: number
  reconstructed_y: number
  reconstructed_z: number
}

export interface GcpAccuracyReport {
  geo_transform: GeoTransform
  point_count: number
  rmse: {
    x_m: number | null
    y_m: number | null
    z_m: number | null
    "3d_m": number | null
  }
  residuals: GcpResidual[]
}

export interface CheckpointResult {
  label: string
  distance_m: number
  nearest_surface_point: string
}

export interface CheckpointValidationReport {
  available: boolean
  source?: string
  point_count?: number
  surface_point_count?: number
  summary?: {
    min_m: number
    max_m: number
    mean_m: number
    rmse_m: number
  }
  checkpoints?: CheckpointResult[]
}
