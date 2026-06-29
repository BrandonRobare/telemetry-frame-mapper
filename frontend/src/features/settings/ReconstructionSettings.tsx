import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import InfoHint from '../../shared/components/InfoHint'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import { useSettings, useUpdateSettings } from './api'
import type { ReconstructionSettings as ReconstructionSettingsType } from './api'
import { hasValidationErrors, validateReconstructionSettings } from './settingsValidation'

interface FieldProps {
  label: string
  hint?: string
  info?: string
  error?: string
  children: React.ReactNode
}
function Field({ label, hint, info, error, children }: FieldProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label className="text-xs font-medium" style={{ color: 'var(--text)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        {label}
        {info && <InfoHint text={info} />}
      </label>
      {children}
      {hint && (
        <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
          {hint}
        </span>
      )}
      {error && (
        <span className="text-xs" style={{ color: 'var(--danger)' }}>
          {error}
        </span>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '5px 8px',
  color: 'var(--text)',
  fontSize: 13,
  fontFamily: 'inherit',
}

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: 'pointer',
  maxWidth: 240,
}

const DEFAULT: ReconstructionSettingsType = {
  default_preset: 'quick',
  colmap_threads: 8,
  sift_max_features: 8192,
  matcher: 'exhaustive',
  camera_model: 'PINHOLE',
  presets: {
    quick: { iterations: 1000, max_frames: 500, max_gaussians: 350000, sh_degree: 1, downscale_factor: 4 },
    full:  { iterations: 30000, max_frames: null, max_gaussians: 1000000, sh_degree: 2, downscale_factor: 2 },
  },
}

export default function ReconstructionSettings() {
  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  const [edits, setEdits] = useState<Partial<Omit<ReconstructionSettingsType, 'presets'>>>({})
  const dirty = Object.keys(edits).length > 0

  const server = settings?.reconstruction ?? DEFAULT
  const form: ReconstructionSettingsType = { ...server, ...edits }
  const presetKeys = Object.keys(form.presets)
  const validationErrors = validateReconstructionSettings(form)
  const hasErrors = hasValidationErrors(validationErrors)

  function updateTop<K extends keyof Omit<ReconstructionSettingsType, 'presets'>>(
    key: K,
    value: ReconstructionSettingsType[K]
  ) {
    setEdits((e) => ({ ...e, [key]: value }))
  }

  function handleSave() {
    if (hasErrors) return
    updateMutation.mutate(
      { reconstruction: form },
      { onSuccess: () => setEdits({}) }
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p className="text-xs" style={{ color: 'var(--text-faint)', margin: 0 }}>
        Applies to new reconstruction jobs only. Running jobs are not affected.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Default Preset" error={validationErrors.default_preset}>
          <select
            value={form.default_preset}
            onChange={(e) => updateTop('default_preset', e.target.value)}
            style={selectStyle}
          >
            {presetKeys.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label="COLMAP Threads"
          hint="Number of parallel threads for COLMAP feature extraction"
          error={validationErrors.colmap_threads}
        >
          <input
            type="number"
            min={1}
            max={64}
            value={form.colmap_threads}
            onChange={(e) => updateTop('colmap_threads', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>

        <Field
          label="SIFT Max Features"
          hint="Maximum features extracted per image"
          info="More features = more detail and slower matching. 8192 is a good default."
          error={validationErrors.sift_max_features}
        >
          <input
            type="number"
            min={256}
            step={256}
            value={form.sift_max_features}
            onChange={(e) => updateTop('sift_max_features', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 140 }}
          />
        </Field>
      </div>

      <AdvancedDisclosure>
        <Field
          label="Feature Matcher"
          info="Sequential matches neighbouring frames (fast, for video); Exhaustive matches all pairs (slower, more robust)."
          error={validationErrors.matcher}
        >
          <select
            value={form.matcher}
            onChange={(e) => updateTop('matcher', e.target.value)}
            style={selectStyle}
          >
            <option value="exhaustive">Exhaustive (best quality)</option>
            <option value="sequential">Sequential (faster, ordered frames)</option>
          </select>
        </Field>

        <Field
          label="Camera Model"
          info="PINHOLE solves focal length + principal point; SIMPLE_PINHOLE assumes a centered principal point."
          error={validationErrors.camera_model}
        >
          <select
            value={form.camera_model}
            onChange={(e) => updateTop('camera_model', e.target.value)}
            style={selectStyle}
          >
            <option value="PINHOLE">PINHOLE (fx, fy, cx, cy)</option>
            <option value="SIMPLE_PINHOLE">SIMPLE_PINHOLE (f, cx, cy)</option>
          </select>
        </Field>
      </AdvancedDisclosure>

      {dirty && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            variant="primary"
            size="sm"
            disabled={updateMutation.isPending || hasErrors}
            onClick={handleSave}
          >
            {updateMutation.isPending ? 'Saving…' : 'Save changes'}
          </Button>
          {updateMutation.isError && (
            <span className="text-xs" style={{ color: 'var(--danger)' }}>
              {(updateMutation.error as Error).message}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
