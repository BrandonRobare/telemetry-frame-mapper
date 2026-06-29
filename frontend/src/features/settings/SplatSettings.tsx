import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import InfoHint from '../../shared/components/InfoHint'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import { useSettings, useUpdateSettings } from './api'
import type { ReconstructionSettings, PresetConfig } from './api'
import { hasValidationErrors, validatePresetConfig } from './settingsValidation'

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
  maxWidth: 140,
}

const DEFAULT_PRESETS: Record<string, PresetConfig> = {
  quick: { iterations: 1000, max_frames: 500, max_gaussians: 350000, sh_degree: 1, downscale_factor: 4 },
  full:  { iterations: 30000, max_frames: null, max_gaussians: 1000000, sh_degree: 2, downscale_factor: 2 },
}

const DEFAULT_RECONSTRUCTION: ReconstructionSettings = {
  default_preset: 'quick',
  colmap_threads: 8,
  sift_max_features: 8192,
  matcher: 'exhaustive',
  camera_model: 'PINHOLE',
  presets: DEFAULT_PRESETS,
}

// Splat Training edits the `presets` sub-object inside reconstruction settings.
// We track a local overrides map keyed by preset name.
export default function SplatSettings() {
  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  // presetEdits[name] holds partial overrides per preset
  const [presetEdits, setPresetEdits] = useState<Record<string, Partial<PresetConfig>>>({})
  const dirty = Object.keys(presetEdits).some((k) => Object.keys(presetEdits[k]).length > 0)

  const serverPresets = settings?.reconstruction?.presets ?? DEFAULT_PRESETS
  // Merge edits into server data for display
  const displayPresets: Record<string, PresetConfig> = Object.fromEntries(
    Object.entries(serverPresets).map(([name, cfg]) => [
      name,
      { ...cfg, ...(presetEdits[name] ?? {}) },
    ])
  )
  const validationErrors: Record<string, ReturnType<typeof validatePresetConfig>> = Object.fromEntries(
    Object.entries(displayPresets).map(([name, cfg]) => [name, validatePresetConfig(cfg)])
  )
  const hasErrors = Object.values(validationErrors).some(hasValidationErrors)

  function updatePreset<K extends keyof PresetConfig>(
    name: string,
    key: K,
    value: PresetConfig[K]
  ) {
    setPresetEdits((p) => ({
      ...p,
      [name]: { ...(p[name] ?? {}), [key]: value },
    }))
  }

  function handleSave() {
    if (hasErrors) return
    const existing = settings?.reconstruction ?? DEFAULT_RECONSTRUCTION
    const updatedPresets: Record<string, PresetConfig> = Object.fromEntries(
      Object.entries(serverPresets).map(([name, cfg]) => [
        name,
        { ...cfg, ...(presetEdits[name] ?? {}) },
      ])
    )
    const updated: ReconstructionSettings = { ...existing, presets: updatedPresets }
    updateMutation.mutate(
      { reconstruction: updated },
      { onSuccess: () => setPresetEdits({}) }
    )
  }

  const presetKeys = Object.keys(displayPresets)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <p className="text-xs" style={{ color: 'var(--text-faint)', margin: 0 }}>
        Applies to new splat training jobs only — running jobs are not affected.
      </p>

      {presetKeys.map((name) => {
        const p = displayPresets[name]
        return (
          <section key={name}>
            <h4
              className="text-xs font-semibold uppercase"
              style={{ color: 'var(--text-muted)', letterSpacing: '0.06em', margin: '0 0 12px' }}
            >
              {name} preset
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <Field label="Iterations" error={validationErrors[name]?.iterations}>
                <input
                  type="number"
                  min={100}
                  step={100}
                  value={p.iterations}
                  onChange={(e) => updatePreset(name, 'iterations', Number(e.target.value))}
                  style={inputStyle}
                />
              </Field>

              <Field
                label="Max Frames"
                hint="Leave blank for no limit (full preset)"
                error={validationErrors[name]?.max_frames}
              >
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={p.max_frames ?? ''}
                  placeholder="unlimited"
                  onChange={(e) =>
                    updatePreset(
                      name,
                      'max_frames',
                      e.target.value === '' ? null : Number(e.target.value)
                    )
                  }
                  style={inputStyle}
                />
              </Field>

              <AdvancedDisclosure>
                <Field
                  label="Max Gaussians"
                  info="Caps the splat count; higher is sharper but uses more VRAM."
                  error={validationErrors[name]?.max_gaussians}
                >
                  <input
                    type="number"
                    min={1000}
                    step={10000}
                    value={p.max_gaussians}
                    onChange={(e) => updatePreset(name, 'max_gaussians', Number(e.target.value))}
                    style={inputStyle}
                  />
                </Field>

                <Field
                  label="SH Degree"
                  hint="Spherical harmonics degree (1-3)"
                  info="Higher captures more view-dependent colour at higher memory cost."
                  error={validationErrors[name]?.sh_degree}
                >
                  <input
                    type="number"
                    min={1}
                    max={3}
                    value={p.sh_degree}
                    onChange={(e) => updatePreset(name, 'sh_degree', Number(e.target.value))}
                    style={inputStyle}
                  />
                </Field>

                <Field
                  label="Downscale Factor"
                  hint="Image downscaling before training (1 = full res)"
                  info="Trains on downscaled images for speed; 1 = full resolution."
                  error={validationErrors[name]?.downscale_factor}
                >
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={p.downscale_factor}
                    onChange={(e) => updatePreset(name, 'downscale_factor', Number(e.target.value))}
                    style={inputStyle}
                  />
                </Field>
              </AdvancedDisclosure>
            </div>
          </section>
        )
      })}

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
