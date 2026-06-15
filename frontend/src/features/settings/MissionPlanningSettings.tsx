import { useState } from 'react'
import { Button } from '../../shared/components/Button'
import { useSettings, useUpdateSettings } from './api'
import type { MissionSettings } from './api'

interface FieldProps {
  label: string
  hint?: string
  children: React.ReactNode
}
function Field({ label, hint, children }: FieldProps) {
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
  maxWidth: 160,
}

const DEFAULT: MissionSettings = {
  altitude_ft: 200,
  fov_horizontal_deg: 83,
  fov_vertical_deg: 53,
  image_width_px: 4000,
  image_height_px: 3000,
  desired_side_overlap: 0.70,
  desired_forward_overlap: 0.80,
  lane_spacing_ft: 105,
  default_video_fps: 2.0,
  battery_range_m: 3000,
  mission_buffer_pct: 0.10,
  flight_log_match_tolerance_sec: 2.0,
}

export default function MissionPlanningSettings() {
  const { data: settings } = useSettings()
  const updateMutation = useUpdateSettings()

  const [edits, setEdits] = useState<Partial<MissionSettings>>({})
  const dirty = Object.keys(edits).length > 0

  const server = settings?.mission ?? DEFAULT
  const form: MissionSettings = { ...server, ...edits }

  function updateForm<K extends keyof MissionSettings>(key: K, value: MissionSettings[K]) {
    setEdits((e) => ({ ...e, [key]: value }))
  }

  function handleSave() {
    updateMutation.mutate(
      { mission: form },
      { onSuccess: () => setEdits({}) }
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: 16,
        }}
      >
        <Field label="Default Altitude (ft)">
          <input
            type="number"
            step={1}
            min={0}
            value={form.altitude_ft}
            onChange={(e) => updateForm('altitude_ft', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="FOV Horizontal (°)">
          <input
            type="number"
            step={0.1}
            min={0}
            max={180}
            value={form.fov_horizontal_deg}
            onChange={(e) => updateForm('fov_horizontal_deg', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="FOV Vertical (°)">
          <input
            type="number"
            step={0.1}
            min={0}
            max={180}
            value={form.fov_vertical_deg}
            onChange={(e) => updateForm('fov_vertical_deg', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Image Width (px)">
          <input
            type="number"
            step={1}
            min={1}
            value={form.image_width_px}
            onChange={(e) => updateForm('image_width_px', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Image Height (px)">
          <input
            type="number"
            step={1}
            min={1}
            value={form.image_height_px}
            onChange={(e) => updateForm('image_height_px', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Side Overlap" hint="0–1 (e.g. 0.70 = 70%)">
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            value={form.desired_side_overlap}
            onChange={(e) => updateForm('desired_side_overlap', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Forward Overlap" hint="0–1 (e.g. 0.80 = 80%)">
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            value={form.desired_forward_overlap}
            onChange={(e) => updateForm('desired_forward_overlap', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Lane Spacing (ft)">
          <input
            type="number"
            step={1}
            min={0}
            value={form.lane_spacing_ft}
            onChange={(e) => updateForm('lane_spacing_ft', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Default Video FPS">
          <input
            type="number"
            step={0.5}
            min={0.1}
            value={form.default_video_fps}
            onChange={(e) => updateForm('default_video_fps', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Battery Range (m)" hint="Max flight distance per battery">
          <input
            type="number"
            step={100}
            min={0}
            value={form.battery_range_m}
            onChange={(e) => updateForm('battery_range_m', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Mission Buffer" hint="0–1 safety margin on battery range">
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            value={form.mission_buffer_pct}
            onChange={(e) => updateForm('mission_buffer_pct', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>

        <Field label="Flight Log Tolerance (s)" hint="Match window between video timestamp and flight log">
          <input
            type="number"
            step={0.5}
            min={0}
            value={form.flight_log_match_tolerance_sec}
            onChange={(e) => updateForm('flight_log_match_tolerance_sec', Number(e.target.value))}
            style={inputStyle}
          />
        </Field>
      </div>

      {dirty && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            variant="primary"
            size="sm"
            disabled={updateMutation.isPending}
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
