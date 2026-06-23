import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import { useMapStore } from '../../shared/stores/mapStore'
import { useSettingsStore } from './settingsStore'
import { useSettings, useUpdateSettings } from './api'
import type { GeneralSettings as GeneralSettingsType } from './api'
import type { SettingsTab, Units, CoordFormat } from './settingsStore'
import { hasValidationErrors, validateGeneralSettings } from './settingsValidation'

// Shared inline field component
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
  width: '100%',
}

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: 'pointer',
}

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'map', label: 'Map' },
  { id: 'gps-sync', label: 'GPS Sync' },
  { id: 'review', label: 'Review' },
  { id: 'plan', label: 'Plan' },
  { id: 'export', label: 'Export' },
  { id: 'session-log', label: 'Session Log' },
  { id: 'reconstruct', label: 'Reconstruct' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'storage', label: 'Storage' },
  { id: 'splat', label: 'Splat Viewer' },
  { id: 'compare', label: 'Compare' },
  { id: 'settings', label: 'Settings' },
]

const BASEMAPS = [
  { id: 'esri_satellite', label: 'ESRI Satellite' },
  { id: 'osm', label: 'OpenStreetMap' },
  { id: 'mapbox_satellite', label: 'Mapbox Satellite' },
  { id: 'mapbox_streets', label: 'Mapbox Streets' },
]

const GENERAL_DEFAULTS: GeneralSettingsType = {
  default_basemap: 'esri_satellite',
  target_crs: 'EPSG:32617',
  imports_dir: './imports',
  processed_dir: './processed',
  exports_dir: './exports',
  data_dir: './data',
}

export default function GeneralSettings() {
  const { theme, toggleTheme } = useMapStore()
  const {
    defaultTab, units, coordFormat, coordPrecision, reducedMotion, apiBaseUrl,
    setDefaultTab, setUnits, setCoordFormat, setCoordPrecision, setReducedMotion, setApiBaseUrl,
  } = useSettingsStore()

  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  // Local edits on top of the server data — only tracks what the user has changed.
  const [edits, setEdits] = useState<Partial<GeneralSettingsType>>({})
  const dirty = Object.keys(edits).length > 0

  // Effective form value: server data merged with local edits
  const server = settings?.general ?? GENERAL_DEFAULTS
  const form: GeneralSettingsType = { ...server, ...edits }
  const validationErrors = validateGeneralSettings(form)
  const hasErrors = hasValidationErrors(validationErrors)

  function updateForm(key: keyof GeneralSettingsType, value: string) {
    setEdits((e) => ({ ...e, [key]: value }))
  }

  function handleSave() {
    if (hasErrors) return
    updateMutation.mutate(
      { general: form },
      { onSuccess: () => setEdits({}) }
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* -- GUI-only prefs (localStorage) -- */}
      <section>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)', margin: '0 0 14px' }}>
          Appearance &amp; Display
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Theme">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className="text-sm" style={{ color: 'var(--text)' }}>
                {theme === 'light' ? 'Light' : 'Dark'}
              </span>
              <button
                type="button"
                onClick={toggleTheme}
                className="text-xs cursor-pointer rounded"
                style={{
                  padding: '4px 10px',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  fontFamily: 'inherit',
                }}
              >
                Toggle
              </button>
              <span className="text-xs" style={{ color: 'var(--text-faint)' }}>
                Light (Dark coming soon)
              </span>
            </div>
          </Field>

          <Field label="Reduced Motion" hint="Disables animation transitions throughout the app">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={reducedMotion}
                onChange={(e) => setReducedMotion(e.target.checked)}
                style={{ accentColor: 'var(--accent)', width: 14, height: 14 }}
              />
              <span className="text-sm" style={{ color: 'var(--text)' }}>
                Enable reduced motion
              </span>
            </label>
          </Field>

          <Field label="Default Landing Tab" hint="Which tab opens when you first load the app">
            <select
              value={defaultTab}
              onChange={(e) => setDefaultTab(e.target.value as SettingsTab)}
              style={{ ...selectStyle, maxWidth: 260 }}
            >
              {TABS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Units" hint="Display-only — does not affect stored data">
            <select
              value={units}
              onChange={(e) => setUnits(e.target.value as Units)}
              style={{ ...selectStyle, maxWidth: 180 }}
            >
              <option value="feet">Feet</option>
              <option value="meters">Meters</option>
            </select>
          </Field>

          <Field label="Coordinate Format">
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <select
                value={coordFormat}
                onChange={(e) => setCoordFormat(e.target.value as CoordFormat)}
                style={{ ...selectStyle, maxWidth: 180 }}
              >
                <option value="decimal">Decimal Degrees</option>
                <option value="dms">DMS (°  ′  ″)</option>
              </select>
              {coordFormat === 'decimal' && (
                <Field label="Decimal places">
                  <input
                    type="number"
                    min={2}
                    max={10}
                    value={coordPrecision}
                    onChange={(e) => setCoordPrecision(Number(e.target.value))}
                    style={{ ...inputStyle, maxWidth: 80 }}
                  />
                </Field>
              )}
            </div>
          </Field>

          <Field label="API Base URL" hint="Override the backend URL (leave blank for default)">
            <input
              type="text"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
              placeholder="http://localhost:8000"
              style={{ ...inputStyle, maxWidth: 360 }}
            />
          </Field>
        </div>
      </section>

      {/* -- Backend fields -- */}
      <section>
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text)', margin: '0 0 14px' }}>
          Map &amp; Storage
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="Default Basemap">
            <select
              value={form.default_basemap}
              onChange={(e) => updateForm('default_basemap', e.target.value)}
              style={{ ...selectStyle, maxWidth: 260 }}
            >
              {BASEMAPS.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Target CRS"
            hint="Coordinate reference system used for exports and area calculations"
            error={validationErrors.target_crs}
          >
            <input
              type="text"
              value={form.target_crs}
              onChange={(e) => updateForm('target_crs', e.target.value)}
              style={{ ...inputStyle, maxWidth: 240 }}
              placeholder="EPSG:32617"
            />
          </Field>

          <Field label="Imports Directory" error={validationErrors.imports_dir}>
            <input
              type="text"
              value={form.imports_dir}
              onChange={(e) => updateForm('imports_dir', e.target.value)}
              style={{ ...inputStyle, maxWidth: 480 }}
            />
          </Field>

          <Field label="Processed Directory" error={validationErrors.processed_dir}>
            <input
              type="text"
              value={form.processed_dir}
              onChange={(e) => updateForm('processed_dir', e.target.value)}
              style={{ ...inputStyle, maxWidth: 480 }}
            />
          </Field>

          <Field label="Exports Directory" error={validationErrors.exports_dir}>
            <input
              type="text"
              value={form.exports_dir}
              onChange={(e) => updateForm('exports_dir', e.target.value)}
              style={{ ...inputStyle, maxWidth: 480 }}
            />
          </Field>

          <Field label="Data Directory" error={validationErrors.data_dir}>
            <input
              type="text"
              value={form.data_dir}
              onChange={(e) => updateForm('data_dir', e.target.value)}
              style={{ ...inputStyle, maxWidth: 480 }}
            />
          </Field>
        </div>
      </section>

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
