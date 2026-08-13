import { useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiUrl, post, get } from '../../shared/api/client'
import { useToast } from '../../shared/hooks/useToast'
import { Button } from '../../shared/components/Button'
import TabHeader from '../../shared/components/TabHeader'
import FlightSettingsPanel, { type FlightSettings } from './FlightSettingsPanel'
import ShutterIntervalPanel from './ShutterIntervalPanel'
import WeatherAdvisorPanel from './WeatherAdvisorPanel'
import PlanMap from './PlanMap'
import { computeCentroid, type CentroidGeometry } from './weatherAdvisor'
import { parseRenderableGeoJSON } from '../../shared/utils/geojson'


interface TargetAreaOut {
  id: number
  name: string
  geom_geojson: string | null
}

interface PlanOut {
  id: number
  target_area_id: number
  altitude_ft: number | null
  side_overlap_pct: number | null
  forward_overlap_pct: number | null
  lane_count: number | null
  total_distance_m: number | null
  batteries_estimated: number | null
  lanes_geojson: string | null
  kml_path: string | null
  gpx_path: string | null
}

interface ValidationOut {
  plan_id: number
  valid: boolean
  warnings: string[]
  violations: string[]
  info: string[]
}

interface SegmentOut {
  index: number
  from_lane: number
  to_lane: number
  distance_m: number
  landing_wpt: number[] | null
  resume_wpt: number[] | null
  lanes_geojson: string | null
  kml_path: string | null
  gpx_path: string | null
}

const DEFAULT_SETTINGS: FlightSettings = {
  altitudeFt: 200,
  sideOverlapPct: 75,
  forwardOverlapPct: 80,
}

function fmt(n: number | null | undefined, unit: string, decimals = 0) {
  if (n == null) return '—'
  return `${n.toFixed(decimals)} ${unit}`
}

export default function PlanTab() {
  const { addToast } = useToast()
  const [settings, setSettings] = useState<FlightSettings>(DEFAULT_SETTINGS)
  const [targetAreaId, setTargetAreaId] = useState<number | null>(null)
  const [plan, setPlan] = useState<PlanOut | null>(null)
  const [validation, setValidation] = useState<ValidationOut | null>(null)
  const [segments, setSegments] = useState<SegmentOut[] | null>(null)
  const [coverageRunId, setCoverageRunId] = useState<number | null>(null)  // re-fly source
  const [drawnGeometry, setDrawnGeometry] = useState<CentroidGeometry | null>(null)

  // Step 1: create target area from drawn polygon
  const createArea = useMutation({
    mutationFn: (geomGeoJSON: string) =>
      post<TargetAreaOut>('/target-areas/', {
        name: `Plan Area ${new Date().toLocaleDateString()}`,
        geom_geojson: geomGeoJSON,
      }),
    onSuccess: (area) => {
      setTargetAreaId(area.id)
      setPlan(null)
      setValidation(null)
      setSegments(null)
      addToast('Target area saved', 'success')
    },
    onError: () => addToast('Failed to save target area', 'error'),
  })

  // Step 2: generate mission plan
  const generatePlan = useMutation({
    mutationFn: () => {
      if (!targetAreaId) throw new Error('No target area')
      return post<PlanOut>('/plans/generate', {
        target_area_id: targetAreaId,
        altitude_ft: settings.altitudeFt,
        side_overlap_pct: settings.sideOverlapPct / 100,
        forward_overlap_pct: settings.forwardOverlapPct / 100,
      })
    },
    onSuccess: (result) => {
      setPlan(result)
      setValidation(null)
      setSegments(null)
      addToast('Mission plan generated', 'success')
    },
    onError: (e: Error) => addToast(e.message || 'Plan generation failed', 'error'),
  })

  // Validate plan
  const runValidation = useMutation({
    mutationFn: async () => {
      if (!plan) throw new Error('No plan')
      return post<ValidationOut>(`/plans/${plan.id}/validate`)
    },
    onSuccess: (result) => {
      setValidation(result)
      if (!result.valid) {
        addToast('Plan has violations', 'error')
      } else if (result.warnings.length > 0) {
        addToast(`Plan valid with ${result.warnings.length} warning(s)`, 'info')
      } else {
        addToast('Plan validated — no issues', 'success')
      }
    },
    onError: (e: Error) => addToast(e.message || 'Validation failed', 'error'),
  })

  // Fetch segments
  const fetchSegments = useMutation({
    mutationFn: async () => {
      if (!plan) throw new Error('No plan')
      return get<SegmentOut[]>(`/plans/${plan.id}/segments`)
    },
    onSuccess: (result) => {
      setSegments(result)
      addToast(`${result.length} segment(s) found`, 'success')
    },
    onError: (e: Error) => addToast(e.message || 'Failed to fetch segments', 'error'),
  })

  // Re-fly from coverage gaps
  const generateRefly = useMutation({
    mutationFn: (covRunId: number) =>
      post<PlanOut>('/plans/generate-from-gaps', {
        coverage_run_id: covRunId,
        altitude_ft: settings.altitudeFt,
        side_overlap_pct: settings.sideOverlapPct / 100,
        forward_overlap_pct: settings.forwardOverlapPct / 100,
      }),
    onSuccess: (result) => {
      setPlan(result)
      setValidation(null)
      setSegments(null)
      addToast('Re-fly plan generated from gaps', 'success')
    },
    onError: (e: Error) => addToast(e.message || 'Re-fly generation failed', 'error'),
  })

  const lanesGeoJSON = useMemo(() => {
    return parseRenderableGeoJSON(plan?.lanes_geojson)
  }, [plan])
  const isBusy = createArea.isPending || generatePlan.isPending

  function handlePolygonDrawn(geojsonStr: string) {
    try {
      setDrawnGeometry(JSON.parse(geojsonStr) as CentroidGeometry)
    } catch {
      setDrawnGeometry(null)
    }
    createArea.mutate(geojsonStr)
  }

  const weatherCentroid = computeCentroid(drawnGeometry)

  function downloadFile(url: string) {
    window.open(url, '_blank')
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Plan"
        description="Draw a target area and generate a flight plan (KML/GPX)."
      />
      <div className="fm-plan-layout flex flex-1 overflow-hidden">
      {/* Left panel */}
      <div
        className="fm-plan-panel flex flex-col shrink-0 overflow-y-auto"
        style={{
          width: 300,
          padding: 20,
          borderRight: '1px solid var(--border)',
          background: 'var(--surface)',
          gap: 0,
        }}
      >
        {/* Draw hint */}
        <div
          className="text-xs rounded"
          style={{
            padding: '8px 12px',
            marginBottom: 20,
            background: 'var(--accent-soft)',
            border: '1px solid var(--accent-soft)',
            color: 'var(--text-muted)',
          }}
        >
          {targetAreaId
            ? '✓ Target area saved. Adjust settings and generate plan.'
            : 'Use the polygon tool (top-left of the map) to draw your target area.'}
        </div>

        <FlightSettingsPanel settings={settings} onChange={setSettings} disabled={isBusy} />

        <ShutterIntervalPanel
          altitudeFt={settings.altitudeFt}
          forwardOverlapPct={settings.forwardOverlapPct}
        />

        <WeatherAdvisorPanel
          lat={weatherCentroid?.lat ?? null}
          lon={weatherCentroid?.lon ?? null}
        />

        {/* Re-fly section */}
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input
              type="number"
              placeholder="Coverage run ID"
              className="text-xs"
              style={{
                flex: 1,
                padding: '4px 8px',
                border: '1px solid var(--border)',
                background: 'var(--surface-2)',
                color: 'var(--text)',
              }}
              value={coverageRunId ?? ''}
              onChange={(e) => setCoverageRunId(e.target.value ? Number(e.target.value) : null)}
            />
            <Button
              variant="ghost"
              size="sm"
              disabled={!coverageRunId || generateRefly.isPending}
              onClick={() => coverageRunId && generateRefly.mutate(coverageRunId)}
            >
              Re-fly
            </Button>
          </div>
        </div>

        <div style={{ marginTop: 8 }}>
          <Button
            variant="primary"
            size="sm"
            style={{ width: '100%' }}
            disabled={!targetAreaId || isBusy}
            onClick={() => generatePlan.mutate()}
          >
            {generatePlan.isPending ? 'Generating…' : 'Generate Plan'}
          </Button>
        </div>

        {/* Plan summary */}
        {plan && (
          <div
            style={{
              marginTop: 20,
              padding: '12px 14px',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
            }}
          >
            <h4 className="text-xs font-semibold" style={{ color: 'var(--text)', marginBottom: 10 }}>
              Plan Summary
            </h4>
            {[
              ['Lanes', plan.lane_count ?? '—'],
              ['Total distance', fmt(plan.total_distance_m, 'm')],
              [
                'Est. batteries',
                plan.batteries_estimated != null
                  ? plan.batteries_estimated.toFixed(2)
                  : '—',
              ],
              ['Altitude', fmt(plan.altitude_ft, 'ft')],
              [
                'Side overlap',
                plan.side_overlap_pct != null
                  ? `${(plan.side_overlap_pct * 100).toFixed(0)}%`
                  : '—',
              ],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex justify-between text-xs" style={{ marginBottom: 6 }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{String(value)}</span>
              </div>
            ))}

            {/* Action buttons */}
            <div className="flex gap-2" style={{ marginTop: 12, marginBottom: 8 }}>
              <Button
                variant="ghost"
                size="sm"
                style={{ flex: 1 }}
                disabled={!plan.kml_path}
                onClick={() => downloadFile(apiUrl(`/plans/${plan.id}/kml`))}
              >
                KML ↓
              </Button>
              <Button
                variant="ghost"
                size="sm"
                style={{ flex: 1 }}
                disabled={!plan.gpx_path}
                onClick={() => downloadFile(apiUrl(`/plans/${plan.id}/gpx`))}
              >
                GPX ↓
              </Button>
            </div>

            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                style={{ flex: 1 }}
                disabled={!plan.id || runValidation.isPending}
                onClick={() => runValidation.mutate()}
              >
                {runValidation.isPending ? 'Validating…' : 'Validate'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                style={{ flex: 1 }}
                disabled={!plan.id || fetchSegments.isPending}
                onClick={() => fetchSegments.mutate()}
              >
                {fetchSegments.isPending ? 'Loading…' : 'Segments'}
              </Button>
            </div>
          </div>
        )}

        {/* Validation results */}
        {validation && (
          <div
            style={{
              marginTop: 12,
              padding: '12px 14px',
              background: validation.valid ? 'var(--surface-2)' : 'var(--error-soft, #fef2f2)',
              border: `1px solid ${validation.valid ? 'var(--border)' : 'var(--error, #dc2626)'}`,
            }}
          >
            <h4 className="text-xs font-semibold" style={{ color: 'var(--text)', marginBottom: 10 }}>
              {validation.valid ? 'Validation — Passed' : 'Validation — FAILED'}
            </h4>
            {validation.violations.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <span className="text-xs" style={{ color: 'var(--error, #dc2626)', fontWeight: 600 }}>
                  Violations:
                </span>
                {validation.violations.map((v, i) => (
                  <div key={i} className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    • {v}
                  </div>
                ))}
              </div>
            )}
            {validation.warnings.length > 0 && (
              <div style={{ marginBottom: validation.info.length > 0 ? 8 : 0 }}>
                <span className="text-xs" style={{ color: 'var(--warning, #d97706)', fontWeight: 600 }}>
                  Warnings:
                </span>
                {validation.warnings.map((w, i) => (
                  <div key={i} className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    • {w}
                  </div>
                ))}
              </div>
            )}
            {validation.info.length > 0 && (
              <div>
                <span className="text-xs" style={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                  Info:
                </span>
                {validation.info.map((msg, i) => (
                  <div key={i} className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    • {msg}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Segments */}
        {segments && segments.length > 0 && (
          <div
            style={{
              marginTop: 12,
              padding: '12px 14px',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
            }}
          >
            <h4 className="text-xs font-semibold" style={{ color: 'var(--text)', marginBottom: 10 }}>
              Battery Segments ({segments.length})
            </h4>
            {segments.map((seg) => (
              <div
                key={seg.index}
                style={{
                  marginBottom: 10,
                  padding: '8px',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                }}
              >
                <div className="flex justify-between text-xs" style={{ marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Segment {seg.index + 1}</span>
                  <span style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
                    Lanes {seg.from_lane + 1}–{seg.to_lane + 1}
                  </span>
                </div>
                <div className="text-xs" style={{ color: 'var(--text-muted)', marginBottom: 6 }}>
                  {fmt(seg.distance_m, 'm')}
                </div>
                {seg.landing_wpt && (
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Land: [{seg.landing_wpt[0].toFixed(4)}, {seg.landing_wpt[1].toFixed(4)}]
                  </div>
                )}
                {seg.resume_wpt && (
                  <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Resume: [{seg.resume_wpt[0].toFixed(4)}, {seg.resume_wpt[1].toFixed(4)}]
                  </div>
                )}
                <div className="flex gap-2" style={{ marginTop: 6 }}>
                  {seg.kml_path && (
                    <Button
                      variant="ghost"
                      size="sm"
                      style={{ flex: 1, fontSize: '0.7rem' }}
                      onClick={() => downloadFile(apiUrl(`/plans/${plan?.id}/segments/${seg.index}/kml`))}
                    >
                      KML ↓
                    </Button>
                  )}
                  {seg.gpx_path && (
                    <Button
                      variant="ghost"
                      size="sm"
                      style={{ flex: 1, fontSize: '0.7rem' }}
                      onClick={() => downloadFile(apiUrl(`/plans/${plan?.id}/segments/${seg.index}/gpx`))}
                    >
                      GPX ↓
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Map */}
      <div className="fm-plan-map flex-1 relative">
        <PlanMap lanesGeoJSON={lanesGeoJSON} onPolygonDrawn={handlePolygonDrawn} />
        {isBusy && (
          <div
            className="absolute inset-0 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.3)', zIndex: 999 }}
          >
            <span className="text-sm" style={{ color: 'var(--on-accent)' }}>Working…</span>
          </div>
        )}
      </div>
    </div>
    </div>
  )
}