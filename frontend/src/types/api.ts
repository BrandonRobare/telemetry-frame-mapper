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
  status: "pending" | "running_colmap" | "running_gsplat" | "complete" | "failed";
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

export interface Job {
  id: number;
  type: "reconstruction";
  session_id: number;
  status: "pending" | "running_colmap" | "running_gsplat" | "complete" | "failed";
  preset: string;
  progress_pct: number;
  step: string;
  frames_used: number;
  started_at: string | null;
  completed_at: string | null;
  error_msg: string | null;
}

export interface StorageStats {
  total_bytes: number;
  by_type: {
    imports: number;
    processed: number;
    exports: number;
    data: number;
  };
  by_session: unknown[];
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
