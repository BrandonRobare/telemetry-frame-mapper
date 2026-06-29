import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import { useSettings, useUpdateSettings } from './api'
import type { RenderSettings } from './api'
import { hasValidationErrors, validateRenderSettings } from './settingsValidation'

interface FieldProps {
  label: string
  hint?: string
  error?: string
  children: React.ReactNode
}
function Field({ label, hint, error, children }: FieldProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label className="text-xs font-medium" style={{ color: 'var(--text)' }}>
        {label}
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

const DEFAULT: RenderSettings = {
  flythrough_fps: 30,
  flythrough_width: 1920,
  flythrough_height: 1080,
  thumbnail_size_px: 512,
  thumbnail_quality: 85,
  lod_preview_ratio: 0.10,
  lod_medium_ratio: 0.50,
}

export default function RenderExportSettings() {
  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  const [edits, setEdits] = useState<Partial<RenderSettings>>({})
  const dirty = Object.keys(edits).length > 0

  const server = settings?.render ?? DEFAULT
  const form: RenderSettings = { ...server, ...edits }
  const validationErrors = validateRenderSettings(form)
  const hasErrors = hasValidationErrors(validationErrors)

  function updateForm<K extends keyof RenderSettings>(key: K, value: RenderSettings[K]) {
    setEdits((e) => ({ ...e, [key]: value }))
  }

  function handleSave() {
    if (hasErrors) return
    updateMutation.mutate(
      { render: form },
      { onSuccess: () => setEdits({}) }
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <p className="text-xs" style={{ color: 'var(--text-faint)', margin: 0 }}>
        Applies to new render/export jobs only. Running jobs are not affected.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Flythrough FPS" error={validationErrors.flythrough_fps}>
          <input
            type="number"
            min={1}
            max={60}
            value={form.flythrough_fps}
            onChange={(e) => updateForm('flythrough_fps', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Flythrough Width (px)" error={validationErrors.flythrough_width}>
          <input
            type="number"
            min={320}
            step={2}
            value={form.flythrough_width}
            onChange={(e) => updateForm('flythrough_width', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Flythrough Height (px)" error={validationErrors.flythrough_height}>
          <input
            type="number"
            min={240}
            step={2}
            value={form.flythrough_height}
            onChange={(e) => updateForm('flythrough_height', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Thumbnail Size (px)" error={validationErrors.thumbnail_size_px}>
          <input
            type="number"
            min={64}
            max={2048}
            value={form.thumbnail_size_px}
            onChange={(e) => updateForm('thumbnail_size_px', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Thumbnail Quality" hint="JPEG quality 1-100" error={validationErrors.thumbnail_quality}>
          <input
            type="number"
            min={1}
            max={100}
            value={form.thumbnail_quality}
            onChange={(e) => updateForm('thumbnail_quality', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>
      </div>

      <AdvancedDisclosure>
        <Field
          label="LOD Preview Ratio"
          hint="0-1 fraction of gaussians shown in preview LOD"
          error={validationErrors.lod_preview_ratio}
        >
          <input
            type="number"
            step={0.01}
            min={0.01}
            max={1}
            value={form.lod_preview_ratio}
            onChange={(e) => updateForm('lod_preview_ratio', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field
          label="LOD Medium Ratio"
          hint="0-1 fraction of gaussians shown in medium LOD"
          error={validationErrors.lod_medium_ratio}
        >
          <input
            type="number"
            step={0.01}
            min={0.01}
            max={1}
            value={form.lod_medium_ratio}
            onChange={(e) => updateForm('lod_medium_ratio', Number(e.target.value))}
            style={inputStyle}
          />
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
