import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../shared/api/client'

// ---------------------------------------------------------------------------
// TypeScript types for the /settings contract
// ---------------------------------------------------------------------------

export interface GeneralSettings {
  default_basemap: string
  target_crs: string
  imports_dir: string
  processed_dir: string
  exports_dir: string
  data_dir: string
}

export interface MissionSettings {
  altitude_ft: number
  fov_horizontal_deg: number
  fov_vertical_deg: number
  image_width_px: number
  image_height_px: number
  desired_side_overlap: number
  desired_forward_overlap: number
  lane_spacing_ft: number
  default_video_fps: number
  battery_range_m: number
  mission_buffer_pct: number
  flight_log_match_tolerance_sec: number
}

export interface IngestSettings {
  thumbnail_size_px: number
  thumbnail_jpeg_quality: number
  accepted_extensions: string[]
  blur_threshold: number
  dark_threshold: number
  bright_threshold: number
  filter_zero_gps: boolean
}

export interface PresetConfig {
  iterations: number
  max_frames: number | null
  max_gaussians: number
  sh_degree: number
  downscale_factor: number
}

export interface ReconstructionSettings {
  default_preset: string
  colmap_threads: number
  sift_max_features: number
  matcher: string
  camera_model: string
  presets: Record<string, PresetConfig>
}

export interface RenderSettings {
  flythrough_fps: number
  flythrough_width: number
  flythrough_height: number
  thumbnail_size_px: number
  thumbnail_quality: number
  lod_preview_ratio: number
  lod_medium_ratio: number
}

export interface AppSettings {
  general: GeneralSettings
  mission: MissionSettings
  ingest: IngestSettings
  reconstruction: ReconstructionSettings
  render: RenderSettings
}

// ---------------------------------------------------------------------------
// React Query hooks
// ---------------------------------------------------------------------------

export const SETTINGS_KEY = ['settings'] as const

export function useSettings() {
  return useQuery<AppSettings>({
    queryKey: SETTINGS_KEY,
    queryFn: () => get<AppSettings>('/settings'),
  })
}

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch_body: Partial<AppSettings>) =>
      patch<AppSettings>('/settings', patch_body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEY })
    },
  })
}

export function useResetSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<AppSettings>('/settings/reset'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEY })
    },
  })
}
