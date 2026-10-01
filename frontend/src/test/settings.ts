import type { AppSettings } from '../features/settings/api'

export const settingsFixture: AppSettings = {
  general: {
    default_basemap: 'esri_satellite',
    target_crs: 'EPSG:32617',
    imports_dir: './imports',
    processed_dir: './processed',
    exports_dir: './exports',
    data_dir: './data',
  },
  mission: {
    altitude_ft: 200,
    fov_horizontal_deg: 83,
    fov_vertical_deg: 53,
    image_width_px: 4000,
    image_height_px: 3000,
    desired_side_overlap: 0.7,
    desired_forward_overlap: 0.8,
    lane_spacing_ft: 105,
    default_video_fps: 2,
    battery_range_m: 3000,
    mission_buffer_pct: 0.1,
    flight_log_match_tolerance_sec: 2,
  },
  ingest: {
    thumbnail_size_px: 200,
    thumbnail_jpeg_quality: 75,
    accepted_extensions: ['.jpg'],
    blur_threshold: 100,
    dark_threshold: 50,
    bright_threshold: 210,
    filter_zero_gps: true,
  },
  reconstruction: {
    default_preset: 'quick',
    colmap_threads: 8,
    sift_max_features: 8192,
    matcher: 'exhaustive',
    camera_model: 'PINHOLE',
    presets: {
      quick: { iterations: 1250, max_gaussians: 350000, sh_degree: 1, downscale_factor: 4 },
      full: { iterations: 30000, max_gaussians: 1000000, sh_degree: 2, downscale_factor: 2 },
    },
  },
  render: {
    flythrough_fps: 30,
    flythrough_width: 1920,
    flythrough_height: 1080,
    thumbnail_size_px: 512,
    thumbnail_quality: 85,
    lod_preview_ratio: 0.1,
    lod_medium_ratio: 0.5,
  },
}

