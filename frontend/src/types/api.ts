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
