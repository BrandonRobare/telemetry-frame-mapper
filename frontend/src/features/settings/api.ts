import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../shared/api/client'
import { useToast } from '../../shared/hooks/useToast'

import type { AppSettings } from '../../types/api'
import type { components } from '../../types/api.generated'

export type { AppSettings } from '../../types/api'
// Settings form models select editable fields from the full generated read response.
export type GeneralSettings = Pick<components['schemas']['GeneralSettingsRead'], 'default_basemap' | 'target_crs' | 'imports_dir' | 'processed_dir' | 'exports_dir' | 'data_dir'>
export type MissionSettings = components['schemas']['MissionSettingsRead']
export type IngestSettings = Pick<components['schemas']['IngestSettingsRead'], 'thumbnail_size_px' | 'thumbnail_jpeg_quality' | 'accepted_extensions' | 'blur_threshold' | 'dark_threshold' | 'bright_threshold' | 'filter_zero_gps'>
export type PresetConfig = Pick<components['schemas']['PresetConfigRead'], 'iterations' | 'max_gaussians' | 'sh_degree' | 'downscale_factor'>
export type ReconstructionSettings = Pick<components['schemas']['ReconstructionSettingsRead'], 'default_preset' | 'colmap_threads' | 'sift_max_features' | 'matcher' | 'camera_model' | 'presets'>
export type RenderSettings = Pick<components['schemas']['RenderSettingsRead'], 'flythrough_fps' | 'flythrough_width' | 'flythrough_height' | 'thumbnail_size_px' | 'thumbnail_quality' | 'lod_preview_ratio' | 'lod_medium_ratio'>

// PATCH uses the backend's optional field contract; the form still selects editable fields.
export type SettingsPatchBody = components['schemas']['SettingsPatch']
export type ReconstructionSettingsPatch = NonNullable<SettingsPatchBody['reconstruction']>

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
  const { addToast } = useToast()
  return useMutation({
    mutationFn: (patch_body: SettingsPatchBody) =>
      patch<AppSettings>('/settings', patch_body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEY })
    },
    onError: (err: Error) => addToast(err.message || 'Saving settings failed', 'error'),
  })
}

export function useResetSettings() {
  const qc = useQueryClient()
  const { addToast } = useToast()
  return useMutation({
    mutationFn: () => post<AppSettings>('/settings/reset'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SETTINGS_KEY })
    },
    onError: (err: Error) => addToast(err.message || 'Reset failed', 'error'),
  })
}
