import { describe, expect, it } from 'vitest'
import type {
  GeneralSettings,
  IngestSettings,
  MissionSettings,
  PresetConfig,
  ReconstructionSettings,
  RenderSettings,
} from './api'
import {
  hasValidationErrors,
  validateGeneralSettings,
  validateIngestSettings,
  validateMissionSettings,
  validatePresetConfig,
  validateReconstructionSettings,
  validateRenderSettings,
} from './settingsValidation'

const general: GeneralSettings = {
  default_basemap: 'esri_satellite',
  target_crs: 'EPSG:32617',
  imports_dir: './imports',
  processed_dir: './processed',
  exports_dir: './exports',
  data_dir: './data',
}

const mission: MissionSettings = {
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
}

const ingest: IngestSettings = {
  thumbnail_size_px: 200,
  thumbnail_jpeg_quality: 75,
  accepted_extensions: ['.jpg', '.jpeg'],
  blur_threshold: 100,
  dark_threshold: 50,
  bright_threshold: 210,
  filter_zero_gps: true,
}

const reconstruction: ReconstructionSettings = {
  default_preset: 'quick',
  colmap_threads: 8,
  sift_max_features: 8192,
  matcher: 'exhaustive',
  camera_model: 'PINHOLE',
  presets: {},
}

const preset: PresetConfig = {
  iterations: 1000,
  max_frames: 500,
  max_gaussians: 350000,
  sh_degree: 1,
  downscale_factor: 4,
}

const render: RenderSettings = {
  flythrough_fps: 30,
  flythrough_width: 1920,
  flythrough_height: 1080,
  thumbnail_size_px: 512,
  thumbnail_quality: 85,
  lod_preview_ratio: 0.1,
  lod_medium_ratio: 0.5,
}

describe('settings validation', () => {
  it('accepts known-good defaults', () => {
    expect(hasValidationErrors(validateGeneralSettings(general))).toBe(false)
    expect(hasValidationErrors(validateMissionSettings(mission))).toBe(false)
    expect(hasValidationErrors(validateIngestSettings(ingest))).toBe(false)
    expect(hasValidationErrors(validateReconstructionSettings(reconstruction))).toBe(false)
    expect(hasValidationErrors(validatePresetConfig(preset))).toBe(false)
    expect(hasValidationErrors(validateRenderSettings(render))).toBe(false)
  })

  it('flags constrained values before save', () => {
    expect(validateGeneralSettings({ ...general, target_crs: '32617' }).target_crs).toMatch(/EPSG/)
    expect(validateGeneralSettings({ ...general, imports_dir: '' }).imports_dir).toMatch(/required/)
    expect(validateMissionSettings({ ...mission, desired_side_overlap: 1.2 }).desired_side_overlap).toMatch(/at most 1/)
    expect(validateMissionSettings({ ...mission, default_video_fps: 0 }).default_video_fps).toMatch(/at least 1/)
    expect(validateIngestSettings({ ...ingest, thumbnail_jpeg_quality: 101 }).thumbnail_jpeg_quality).toMatch(/at most 100/)
    expect(validateIngestSettings({ ...ingest, accepted_extensions: ['jpg'] }).accepted_extensions).toMatch(/start with a dot/)
    expect(validateReconstructionSettings({ ...reconstruction, matcher: 'spatial' }).matcher).toMatch(/exhaustive/)
    expect(validatePresetConfig({ ...preset, sh_degree: 0 }).sh_degree).toMatch(/at least 1/)
    expect(validateRenderSettings({ ...render, flythrough_fps: 120 }).flythrough_fps).toMatch(/at most 60/)
  })
})
