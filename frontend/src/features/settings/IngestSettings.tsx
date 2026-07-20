import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import { AdvancedDisclosure } from './AdvancedDisclosure'
import { useSettings, useUpdateSettings } from './api'
import type { IngestSettings as IngestSettingsType } from './api'
import { hasValidationErrors, validateIngestSettings } from './settingsValidation'

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
}

const DEFAULT: IngestSettingsType = {
  thumbnail_size_px: 200,
  thumbnail_jpeg_quality: 75,
  accepted_extensions: ['.jpg', '.jpeg'],
  blur_threshold: 100.0,
  dark_threshold: 50.0,
  bright_threshold: 210.0,
  filter_zero_gps: true,
}

export default function IngestSettings() {
  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  // Local edits on top of server data — only tracks changed fields
  const [edits, setEdits] = useState<Partial<IngestSettingsType>>({})
  // accepted_extensions are edited as a comma-string; tracked separately
  const [extStr, setExtStr] = useState<string | null>(null)
  const dirty = Object.keys(edits).length > 0 || extStr !== null

  const server = settings?.ingest ?? DEFAULT
  const form: IngestSettingsType = { ...server, ...edits }
  const validationErrors = validateIngestSettings(form)
  const hasErrors = hasValidationErrors(validationErrors)

  // Effective extensions to display
  const displayExtStr = extStr ?? form.accepted_extensions.join(', ')

  function updateForm<K extends keyof IngestSettingsType>(key: K, value: IngestSettingsType[K]) {
    setEdits((e) => ({ ...e, [key]: value }))
  }

  function handleExtChange(val: string) {
    setExtStr(val)
    const exts = val
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    setEdits((e) => ({ ...e, accepted_extensions: exts }))
  }

  function handleSave() {
    if (hasErrors) return
    updateMutation.mutate(
      { ingest: form },
      {
        onSuccess: () => {
          setEdits({})
          setExtStr(null)
        },
      }
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field
          label="SD-card watch folders"
          hint="Optional auto-import is configured in config.yaml under auto_import. Only listed roots are scanned; restart the backend after changing it."
        >
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Status: GET /auto-import/status
          </span>
        </Field>
        <Field
          label="Thumbnail Size (px)"
          hint="Pixel width/height of generated preview thumbnails"
          error={validationErrors.thumbnail_size_px}
        >
          <input
            type="number"
            min={64}
            max={1024}
            value={form.thumbnail_size_px}
            onChange={(e) => updateForm('thumbnail_size_px', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>
      </div>

      <AdvancedDisclosure>
        <Field
          label="Accepted Extensions"
          hint="Comma-separated list (e.g. .jpg, .jpeg, .tif)"
          error={validationErrors.accepted_extensions}
        >
          <input
            type="text"
            value={displayExtStr}
            onChange={(e) => handleExtChange(e.target.value)}
            style={{ ...inputStyle, maxWidth: 300 }}
          />
        </Field>

        <Field
          label="Thumbnail JPEG Quality"
          hint="1-100; higher = larger file, better quality"
          error={validationErrors.thumbnail_jpeg_quality}
        >
          <input
            type="number"
            min={1}
            max={100}
            value={form.thumbnail_jpeg_quality}
            onChange={(e) => updateForm('thumbnail_jpeg_quality', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>

        <Field label="Blur Threshold" hint="Frames with Laplacian variance below this are flagged blurry">
          <input
            type="number"
            step={0.1}
            value={form.blur_threshold}
            onChange={(e) => updateForm('blur_threshold', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>

        <Field label="Dark Threshold" hint="Mean pixel value below this → flagged dark">
          <input
            type="number"
            step={0.1}
            min={0}
            max={255}
            value={form.dark_threshold}
            onChange={(e) => updateForm('dark_threshold', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>

        <Field label="Bright Threshold" hint="Mean pixel value above this → flagged bright">
          <input
            type="number"
            step={0.1}
            min={0}
            max={255}
            value={form.bright_threshold}
            onChange={(e) => updateForm('bright_threshold', Number(e.target.value))}
            style={{ ...inputStyle, maxWidth: 120 }}
          />
        </Field>

        <Field label="Filter Zero GPS" hint="Skip frames with (0, 0) GPS coordinates during ingest">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={form.filter_zero_gps}
              onChange={(e) => updateForm('filter_zero_gps', e.target.checked)}
              style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
            />
            <span className="text-sm" style={{ color: 'var(--text)' }}>
              Enabled
            </span>
          </label>
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
