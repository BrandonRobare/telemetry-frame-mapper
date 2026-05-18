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
  gps_source: string;
  yaw: number | null;
  gimbal_pitch: number | null;
  width: number | null;
  height: number | null;
  focal_length_mm: number | null;
  sharpness_score: number | null;
  brightness_score: number | null;
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
  error_msg: string | null;
  geo_transform: string | null;
  splat_path: string | null;
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
