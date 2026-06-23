import type {
  GeneralSettings,
  IngestSettings,
  MissionSettings,
  PresetConfig,
  ReconstructionSettings,
  RenderSettings,
} from './api'

export type ValidationErrors<T extends string = string> = Partial<Record<T, string>>

function numberError(value: number, label: string, min?: number, max?: number, minExclusive = false) {
  if (!Number.isFinite(value)) return `${label} must be a number`
  if (min !== undefined && (minExclusive ? value <= min : value < min)) {
    return `${label} must be ${minExclusive ? 'greater than' : 'at least'} ${min}`
  }
  if (max !== undefined && value > max) return `${label} must be at most ${max}`
  return null
}

function pathError(value: string, label: string) {
  if (!value.trim()) return `${label} is required`
  if (value.includes('\0')) return `${label} contains an invalid null character`
  return null
}

function put<T extends string>(errors: ValidationErrors<T>, key: T, message: string | null) {
  if (message) errors[key] = message
}

export function hasValidationErrors(errors: ValidationErrors) {
  return Object.values(errors).some(Boolean)
}

export function validateGeneralSettings(form: GeneralSettings) {
  type Field = keyof GeneralSettings
  const errors: ValidationErrors<Field> = {}

  if (!/^EPSG:\d{4,6}$/i.test(form.target_crs.trim())) {
    errors.target_crs = 'Target CRS must look like EPSG:32617'
  }
  put(errors, 'imports_dir', pathError(form.imports_dir, 'Imports directory'))
  put(errors, 'processed_dir', pathError(form.processed_dir, 'Processed directory'))
  put(errors, 'exports_dir', pathError(form.exports_dir, 'Exports directory'))
  put(errors, 'data_dir', pathError(form.data_dir, 'Data directory'))

  return errors
}

export function validateMissionSettings(form: MissionSettings) {
  type Field = keyof MissionSettings
  const errors: ValidationErrors<Field> = {}

  put(errors, 'desired_side_overlap', numberError(form.desired_side_overlap, 'Side overlap', 0, 1))
  put(errors, 'desired_forward_overlap', numberError(form.desired_forward_overlap, 'Forward overlap', 0, 1))
  put(errors, 'default_video_fps', numberError(form.default_video_fps, 'Default video FPS', 1, 60))
  put(errors, 'mission_buffer_pct', numberError(form.mission_buffer_pct, 'Mission buffer', 0, 1))

  return errors
}

export function validateIngestSettings(form: IngestSettings) {
  type Field = keyof IngestSettings
  const errors: ValidationErrors<Field> = {}

  put(errors, 'thumbnail_size_px', numberError(form.thumbnail_size_px, 'Thumbnail size', 0, undefined, true))
  put(errors, 'thumbnail_jpeg_quality', numberError(form.thumbnail_jpeg_quality, 'Thumbnail JPEG quality', 1, 100))
  if (form.accepted_extensions.length === 0) {
    errors.accepted_extensions = 'Accepted extensions must include at least one extension'
  } else if (form.accepted_extensions.some((ext) => !/^\.[A-Za-z0-9]+$/.test(ext))) {
    errors.accepted_extensions = 'Each extension must start with a dot and contain letters or numbers'
  }

  return errors
}

export function validateReconstructionSettings(form: ReconstructionSettings) {
  type Field = keyof ReconstructionSettings
  const errors: ValidationErrors<Field> = {}

  if (!['quick', 'full'].includes(form.default_preset)) {
    errors.default_preset = 'Default preset must be quick or full'
  }
  put(errors, 'colmap_threads', numberError(form.colmap_threads, 'COLMAP threads', 0, undefined, true))
  put(errors, 'sift_max_features', numberError(form.sift_max_features, 'SIFT max features', 0, undefined, true))
  if (!['exhaustive', 'sequential'].includes(form.matcher)) {
    errors.matcher = 'Feature matcher must be exhaustive or sequential'
  }
  if (!['PINHOLE', 'SIMPLE_PINHOLE'].includes(form.camera_model)) {
    errors.camera_model = 'Camera model must be PINHOLE or SIMPLE_PINHOLE'
  }

  return errors
}

export function validatePresetConfig(form: PresetConfig) {
  type Field = keyof PresetConfig
  const errors: ValidationErrors<Field> = {}

  put(errors, 'iterations', numberError(form.iterations, 'Iterations', 0, undefined, true))
  if (form.max_frames !== null) {
    put(errors, 'max_frames', numberError(form.max_frames, 'Max frames', 0, undefined, true))
  }
  put(errors, 'max_gaussians', numberError(form.max_gaussians, 'Max gaussians', 0, undefined, true))
  put(errors, 'sh_degree', numberError(form.sh_degree, 'SH degree', 1, 3))
  put(errors, 'downscale_factor', numberError(form.downscale_factor, 'Downscale factor', 0, undefined, true))

  return errors
}

export function validateRenderSettings(form: RenderSettings) {
  type Field = keyof RenderSettings
  const errors: ValidationErrors<Field> = {}

  put(errors, 'flythrough_fps', numberError(form.flythrough_fps, 'Flythrough FPS', 1, 60))
  put(errors, 'flythrough_width', numberError(form.flythrough_width, 'Flythrough width', 0, undefined, true))
  put(errors, 'flythrough_height', numberError(form.flythrough_height, 'Flythrough height', 0, undefined, true))
  put(errors, 'thumbnail_size_px', numberError(form.thumbnail_size_px, 'Thumbnail size', 0, undefined, true))
  put(errors, 'thumbnail_quality', numberError(form.thumbnail_quality, 'Thumbnail quality', 1, 100))
  put(errors, 'lod_preview_ratio', numberError(form.lod_preview_ratio, 'LOD preview ratio', 0, 1))
  put(errors, 'lod_medium_ratio', numberError(form.lod_medium_ratio, 'LOD medium ratio', 0, 1))

  return errors
}
