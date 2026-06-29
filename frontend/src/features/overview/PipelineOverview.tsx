import { useState } from 'react'
import { useMapStore } from '../../shared/stores/mapStore'
import { PIPELINE_STAGES, stageColor } from '../../shared/pipeline/stages'
import type { StageKey, StageState } from '../../shared/pipeline/stages'

interface Props {
  stageStates: Record<StageKey, StageState>
  variant?: 'full' | 'compact'
}

const AUX_TOOLS: { label: string; tab: string }[] = [
  { label: 'Plan', tab: 'plan' },
  { label: 'GPS Sync', tab: 'gps-sync' },
  { label: 'Compare', tab: 'compare' },
]

// COLMAP (the "align" stage) uses the warm amber while running, matching the
// status-badge convention; everything else active is terracotta.
function stepColor(key: StageKey, state: StageState): string {
  if (state === 'active' && key === 'align') return '#C8902F'
  return stageColor(state)
}

export default function PipelineOverview({ stageStates, variant = 'full' }: Props) {
  const setRequestedTab = useMapStore((s) => s.setRequestedTab)
  const activeIdx = PIPELINE_STAGES.findIndex(
    (s) => stageStates[s.key] === 'active' || stageStates[s.key] === 'failed',
  )
  const [focus, setFocus] = useState(activeIdx >= 0 ? activeIdx : 0)
  const focusStage = PIPELINE_STAGES[focus]
  const compact = variant === 'compact'
  const dot = compact ? 26 : 32

  return (
    <div style={{ width: '100%' }}>
      <div className="flex items-start" style={{ gap: 0 }}>
        {PIPELINE_STAGES.map((stage, i) => {
          const state = stageStates[stage.key]
          const color = stepColor(stage.key, state)
          const done = state === 'done'
          const active = state === 'active'
          const failed = state === 'failed'
          const filled = done || active || failed
          const nextDone = i < PIPELINE_STAGES.length - 1 && stageStates[PIPELINE_STAGES[i + 1].key] === 'done'
          const connOn = done || nextDone
          return (
            <div key={stage.key} className="flex flex-col items-center" style={{ flex: 1, position: 'relative' }}>
              {i < PIPELINE_STAGES.length - 1 && (
                <div
                  style={{
                    position: 'absolute',
                    top: dot / 2 - 1.5,
                    left: '50%',
                    width: '100%',
                    height: 3,
                    background: connOn
                      ? 'repeating-linear-gradient(90deg, var(--sage) 0 7px, transparent 7px 12px)'
                      : 'var(--border)',
                    transition: 'background var(--dur-slow) var(--ease)',
                    zIndex: 0,
                  }}
                />
              )}
              <button
                onClick={() => setRequestedTab(stage.tab)}
                onMouseEnter={() => setFocus(i)}
                onFocus={() => setFocus(i)}
                aria-label={`${stage.name} — ${stage.description}`}
                className={`cursor-pointer border-none bg-transparent flex flex-col items-center ${active ? 'pl-step-active' : ''}`}
                style={{ zIndex: 1, padding: 0 }}
              >
                <span
                  style={{
                    width: dot,
                    height: dot,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: 'var(--font-mono)',
                    fontSize: compact ? 12 : 13,
                    fontWeight: 500,
                    color: filled ? 'var(--on-accent)' : 'var(--text-faint)',
                    background: filled ? color : 'var(--surface)',
                    border: `2px solid ${filled ? color : 'var(--border-strong)'}`,
                    boxShadow: filled ? 'var(--shadow-1)' : 'none',
                    transition: 'all var(--dur-slow) var(--ease)',
                  }}
                >
                  {failed ? '!' : i + 1}
                </span>
                <span
                  className="mt-2"
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: compact ? 11 : 12,
                    color: i === focus ? 'var(--text)' : 'var(--text-muted)',
                    fontWeight: active || i === focus ? 500 : 400,
                  }}
                >
                  {stage.name}
                </span>
              </button>
            </div>
          )
        })}
      </div>

      {/* Focused-step description */}
      <div
        className="mt-4"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderLeft: '3px solid var(--accent)',
          borderRadius: '0 var(--radius-md) var(--radius-md) 0',
          padding: compact ? '9px 13px' : '11px 15px',
        }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>
            {focus + 1}. {focusStage.name}
          </span>
          <button
            onClick={() => setRequestedTab(focusStage.tab)}
            className="cursor-pointer border-none bg-transparent"
            style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--accent-strong)', padding: 0 }}
          >
            Go to {focusStage.name} →
          </button>
        </div>
        <p className="mt-1" style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.5, margin: '4px 0 0' }}>
          {focusStage.description}
        </p>
      </div>

      {!compact && (
        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <span style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-display)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Tools
          </span>
          {AUX_TOOLS.map((t) => (
            <button
              key={t.tab}
              onClick={() => setRequestedTab(t.tab)}
              className="cursor-pointer transition-all duration-150"
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 12,
                color: 'var(--text-muted)',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: '999px',
                padding: '4px 12px',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--border-strong)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
