import { useState, useEffect, type CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import TabHeader from '../../shared/components/TabHeader'
import EmptyState from '../../shared/components/EmptyState'
import InfoHint from '../../shared/components/InfoHint'
import { FrustumCard, FrustumMark } from '../../shared/components/FrustumCard'
import { ReconstructLoader } from '../../shared/components/Skeleton'
import { useToast } from '../../shared/hooks/useToast'
import { getUrlParam, setUrlParam } from '../../shared/hooks/useUrlState'
import type { Image } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---- inline hooks ----
function useImages(sessionId: number | null) {
  return useQuery<Image[]>({
    queryKey: ['images', sessionId],
    queryFn: () => get<Image[]>(`/images?session_id=${sessionId}`),
    enabled: sessionId !== null,
  })
}

function useFrameSelection(sessionId: number | null) {
  return useQuery<{ image_ids: number[] }>({
    queryKey: ['frame-selection', sessionId],
    queryFn: () => get(`/reconstruction/frame-selection/${sessionId}`),
    enabled: sessionId !== null,
  })
}

function useSetFrameSelection(sessionId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (imageIds: number[]) =>
      post<void>('/reconstruction/frame-selection', { session_id: sessionId, image_ids: imageIds }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['frame-selection', sessionId] }),
  })
}

// Bulk flag/usable edit over many images in a single request (backend /images/bulk).
function useBulkPatch(sessionId: number | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { image_ids: number[]; flag?: string; usable?: boolean }) =>
      patch<{ updated: number }>('/images/bulk', body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ['images', sessionId] })
      const previous = qc.getQueryData<Image[]>(['images', sessionId])
      const ids = new Set(body.image_ids)
      qc.setQueryData<Image[]>(['images', sessionId], (old) =>
        old?.map((im) =>
          ids.has(im.id)
            ? {
                ...im,
                ...(body.flag != null ? { flag: body.flag as Image['flag'] } : {}),
                ...(body.usable != null ? { usable: body.usable } : {}),
              }
            : im,
        ),
      )
      return { previous }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(['images', sessionId], ctx.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['images', sessionId] }),
  })
}

// ---- flag cycling ----
const FLAG_CYCLE: Image['flag'][] = ['good', 'blurry', 'no_gps']

function nextFlag(current: Image['flag']): Image['flag'] {
  const idx = FLAG_CYCLE.indexOf(current)
  if (idx === -1) return 'good'
  return FLAG_CYCLE[(idx + 1) % FLAG_CYCLE.length]
}

// ---- badge colour ----
const FLAG_BADGE: Record<Image['flag'], { bg: string; text: string; label: string }> = {
  good:   { bg: 'var(--success-soft)', text: 'var(--success)',   label: 'Good' },
  blurry: { bg: 'var(--warning-soft)', text: 'var(--warning)',   label: 'Blurry' },
  no_gps: { bg: 'var(--tan-soft)',     text: 'var(--tan-text)',  label: 'No GPS' },
  dark:   { bg: 'var(--surface-2)',    text: 'var(--text-muted)', label: 'Dark' },
  bright: { bg: 'var(--surface-2)',    text: 'var(--text-muted)', label: 'Bright' },
}

// ---- thumb URL helper ----
function thumbUrl(img: Image): string {
  if (img.thumb_path) {
    return `${BASE_URL}/${img.thumb_path.replace(/\\/g, '/')}`
  }
  return ''
}

// ---- filename initials ----
function initials(filename: string): string {
  return filename.slice(0, 2).toUpperCase()
}

// ---- stats bar ----
interface StatsBarProps {
  images: Image[]
  activeFlag: Image['flag'] | null
  onFlagClick: (flag: Image['flag']) => void
  visibleCount: number
  selectedCount: number
  sortBy: 'none' | 'reproj'
  onSortChange: (sort: 'none' | 'reproj') => void
}

function StatsBar({ images, activeFlag, onFlagClick, visibleCount, selectedCount, sortBy, onSortChange }: StatsBarProps) {
  const counts: Record<Image['flag'], number> = {
    good: 0, blurry: 0, no_gps: 0, dark: 0, bright: 0,
  }
  for (const img of images) counts[img.flag]++
  const usableCount = images.filter((img) => img.usable).length

  const items: { label: string; flag: Image['flag']; count: number; color: string }[] = [
    { label: 'Good',   flag: 'good',   count: counts.good,   color: 'var(--success)' },
    { label: 'Blurry', flag: 'blurry', count: counts.blurry, color: 'var(--warning-accent)' },
    { label: 'No GPS', flag: 'no_gps', count: counts.no_gps, color: 'var(--tan-text)' },
    { label: 'Dark',   flag: 'dark',   count: counts.dark,   color: 'var(--text-faint)' },
    { label: 'Bright', flag: 'bright', count: counts.bright, color: 'var(--text-faint)' },
  ]

  return (
    <div
      className="flex gap-6 items-center shrink-0 px-5 py-3 text-sm"
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}
    >
      <span className="flex items-center gap-2" style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
        <FrustumMark size={15} color="var(--accent)" />
        {activeFlag ? `${visibleCount} / ${images.length}` : `${images.length}`} frames
      </span>
      {items.map(({ label, flag, count, color }) => {
        const active = activeFlag === flag
        return (
          <button
            key={flag}
            onClick={() => onFlagClick(flag)}
            className="flex items-center gap-1.5"
            style={{
              background: active ? 'var(--surface-2)' : 'none',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: active ? '2px 6px' : '2px 0',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 'inherit',
              opacity: activeFlag && !active ? 0.45 : 1,
            }}
          >
            <span
              className="inline-block rounded-full shrink-0"
              style={{ width: 8, height: 8, background: color }}
            />
            <span style={{ color: 'var(--text)' }}>{count}</span>
            <span style={{ color: active ? 'var(--text)' : 'var(--text-muted)' }}>{label}</span>
          </button>
        )
      })}
      {activeFlag && (
        <button
          onClick={() => onFlagClick(activeFlag)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: 11, fontFamily: 'inherit',
            padding: 0, marginLeft: -8,
          }}
        >
          ✕ clear
        </button>
      )}
      <button
        onClick={() => onSortChange(sortBy === 'reproj' ? 'none' : 'reproj')}
        style={{
          background: sortBy === 'reproj' ? 'var(--surface-2)' : 'none',
          border: 'none',
          borderRadius: 'var(--radius-sm)',
          padding: '2px 6px',
          cursor: 'pointer',
          fontFamily: 'inherit',
          fontSize: 'inherit',
          color: sortBy === 'reproj' ? 'var(--text)' : 'var(--text-muted)',
        }}
        title="Sort by reprojection error (ascending)"
      >
        ⊕ reproj
      </button>
      <InfoHint text="Reprojection error: how far COLMAP's solved 3D point lands from where the camera actually saw it. Lower is better. Under 1px is good." />
      <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
        {selectedCount > 0 && (
          <span style={{ color: 'var(--accent-strong)', fontWeight: 600, marginRight: 8 }}>
            {selectedCount} selected for reconstruction
          </span>
        )}
        <span style={{ color: 'var(--success)', fontWeight: 600 }}>{usableCount}</span>
        {' / '}{images.length}{' usable'}
      </span>
    </div>
  )
}

// ---- image card ----
interface CardProps {
  img: Image
  sessionId: number
  isSelected: boolean
  onSelect: (id: number, selected: boolean) => void
}

function ImageCard({ img, sessionId, isSelected, onSelect }: CardProps) {
  const qc = useQueryClient()
  const addToast = useToast((s) => s.addToast)

  const flagMutation = useMutation({
    mutationFn: ({ id, flag }: { id: number; flag: string }) =>
      patch<Image>(`/images/${id}`, { flag }),
    onMutate: async ({ id, flag }) => {
      await qc.cancelQueries({ queryKey: ['images', sessionId] })
      const previous = qc.getQueryData<Image[]>(['images', sessionId])
      qc.setQueryData<Image[]>(['images', sessionId], (old) =>
        old?.map((item) => (item.id === id ? { ...item, flag: flag as Image['flag'] } : item))
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(['images', sessionId], context.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['images', sessionId] }),
  })

  const usableMutation = useMutation({
    mutationFn: ({ id, usable }: { id: number; usable: boolean }) =>
      patch<Image>(`/images/${id}`, { usable }),
    onMutate: async ({ id, usable }) => {
      await qc.cancelQueries({ queryKey: ['images', sessionId] })
      const previous = qc.getQueryData<Image[]>(['images', sessionId])
      qc.setQueryData<Image[]>(['images', sessionId], (old) =>
        old?.map((item) => (item.id === id ? { ...item, usable } : item))
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(['images', sessionId], context.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['images', sessionId] }),
  })

  const badge = FLAG_BADGE[img.flag]

  return (
    <div
      className="flex flex-col overflow-hidden"
      style={{
        background: 'var(--surface)',
        border: isSelected
          ? '1px solid var(--accent)'
          : img.usable ? '1px solid var(--border)' : '1px solid var(--danger-accent)',
        position: 'relative',
        minHeight: 152,
      }}
    >
      {/* thumbnail — framed as a camera frustum (the near image plane) */}
      <FrustumCard opacity={img.usable ? 0.5 : 0.28}>
      <div
        className="flex items-center justify-center text-sm font-bold"
        style={{ height: 120, background: 'var(--surface-2)', overflow: 'hidden' }}
      >
        {img.thumb_path ? (
          <img
            src={thumbUrl(img)}
            alt={img.filename}
            style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: img.usable ? 1 : 0.4 }}
            onError={(e) => {
              const target = e.currentTarget
              target.style.display = 'none'
              const parent = target.parentElement
              if (parent && !parent.querySelector('.initials-fallback')) {
                const fb = document.createElement('div')
                fb.className = 'initials-fallback'
                fb.textContent = initials(img.filename)
                fb.style.cssText = 'font-size:1.5rem;color:var(--text-muted);'
                parent.appendChild(fb)
              }
            }}
          />
        ) : (
          <span style={{ color: 'var(--text-muted)', fontSize: '1.5rem' }}>
            {initials(img.filename)}
          </span>
        )}
      </div>
      </FrustumCard>

      {/* flag badge — top-right, clickable */}
      <button
        onClick={() => {
          const prev = img.flag
          const next = nextFlag(prev)
          flagMutation.mutate(
            { id: img.id, flag: next },
            {
              onSuccess: () =>
                addToast(`${img.filename} → ${FLAG_BADGE[next].label}`, 'info', {
                  label: 'Undo',
                  onClick: () => flagMutation.mutate({ id: img.id, flag: prev }),
                }),
            },
          )
        }}
        title="Click to cycle flag"
        aria-label={`Flag: ${badge.label}, click to cycle`}
        disabled={flagMutation.isPending}
        style={{
          position: 'absolute', top: 6, right: 6,
          padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 600,
          border: 'none', cursor: 'pointer',
          background: badge.bg, color: badge.text,
          opacity: flagMutation.isPending ? 0.6 : 1, fontFamily: 'inherit',
        }}
      >
        {badge.label}
      </button>

      {/* filename + scores */}
      <div className="px-2 pt-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
        <div className="truncate" title={img.filename}>{img.filename}</div>
        <div className="flex gap-2 mt-0.5" style={{ fontSize: 10 }}>
          {img.sharpness_score != null && (
            <span title="Sharpness (Laplacian variance)">◈ {img.sharpness_score.toFixed(0)}</span>
          )}
          {img.brightness_score != null && (
            <span title="Brightness (mean pixel 0-255)">☀ {img.brightness_score.toFixed(0)}</span>
          )}
          {img.colmap_error_px != null && (
            <span
              title="COLMAP mean reprojection error"
              style={{
                color: img.colmap_error_px < 1.0
                  ? 'var(--success)'
                  : img.colmap_error_px < 2.0
                  ? 'var(--warning)'
                  : 'var(--danger)',
              }}
            >
              ⊕ {img.colmap_error_px.toFixed(1)}px
            </span>
          )}
        </div>
      </div>

      {/* reconstruction selection checkbox */}
      <label
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          margin: '4px 8px 0', cursor: 'pointer',
          fontSize: 11, color: isSelected ? 'var(--accent-strong)' : 'var(--text-muted)',
          fontFamily: 'inherit',
        }}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(img.id, e.target.checked)}
          style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
        />
        For reconstruction
      </label>

      {/* usable toggle */}
      <button
        onClick={() => {
          const prev = img.usable
          usableMutation.mutate(
            { id: img.id, usable: !prev },
            {
              onSuccess: () =>
                addToast(`${img.filename} → ${!prev ? 'Usable' : 'Skip'}`, 'info', {
                  label: 'Undo',
                  onClick: () => usableMutation.mutate({ id: img.id, usable: prev }),
                }),
            },
          )
        }}
        disabled={usableMutation.isPending}
        style={{
          margin: '4px 8px 8px', padding: '3px 0', borderRadius: 'var(--radius-sm)',
          fontSize: 11, fontWeight: 600, border: 'none', cursor: 'pointer',
          background: img.usable ? 'var(--success-soft)' : 'var(--danger-soft)',
          color: img.usable ? 'var(--success)' : 'var(--danger)',
          opacity: usableMutation.isPending ? 0.6 : 1, fontFamily: 'inherit',
          width: 'calc(100% - 16px)',
        }}
        aria-pressed={img.usable}
        title={img.usable ? 'Mark as skip' : 'Mark as usable'}
      >
        {img.usable ? '✓ Usable' : '✗ Skip'}
      </button>
    </div>
  )
}

// ---- batch selection toolbar ----
function BatchToolbar({
  shownCount,
  usableCount,
  selectedCount,
  onSelectAllShown,
  onSelectUsable,
  onClear,
  onMarkUsable,
  onMarkSkip,
  onSetFlag,
}: {
  shownCount: number
  usableCount: number
  selectedCount: number
  onSelectAllShown: () => void
  onSelectUsable: () => void
  onClear: () => void
  onMarkUsable: () => void
  onMarkSkip: () => void
  onSetFlag: (flag: Image['flag']) => void
}) {
  // Keyboard shortcuts for fast selection on large flights (ignored while typing).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'a') { e.preventDefault(); onSelectAllShown() }
      else if (e.key === 'u') { onSelectUsable() }
      else if (e.key === 'Escape') { onClear() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onSelectAllShown, onSelectUsable, onClear])

  const btn: CSSProperties = {
    background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
    padding: '3px 9px', cursor: 'pointer', color: 'var(--text)', fontFamily: 'var(--font-display)', fontSize: 12,
  }
  const groupLabel: CSSProperties = {
    fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', textTransform: 'uppercase',
  }
  const divider = <span aria-hidden="true" style={{ width: 1, height: 14, background: 'var(--border)', margin: '0 2px', flexShrink: 0 }} />
  return (
    <div
      className="flex items-center gap-2 px-5 py-1.5 shrink-0 overflow-x-auto tg-noscrollbar"
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}
    >
      <span style={groupLabel}>Select</span>
      <button style={btn} onClick={onSelectAllShown}>All shown ({shownCount})</button>
      <button style={btn} onClick={onSelectUsable}>Usable ({usableCount})</button>
      <button style={{ ...btn, opacity: selectedCount === 0 ? 0.5 : 1, cursor: selectedCount === 0 ? 'default' : 'pointer' }} onClick={onClear} disabled={selectedCount === 0}>
        Clear
      </button>
      {divider}
      <span style={groupLabel}>Edit {shownCount} shown</span>
      <button style={btn} onClick={onMarkUsable}>✓ Usable</button>
      <button style={btn} onClick={onMarkSkip}>✗ Skip</button>
      <span style={{ ...groupLabel, textTransform: 'none' }}>flag →</span>
      <button style={btn} onClick={() => onSetFlag('good')}>Good</button>
      <button style={btn} onClick={() => onSetFlag('blurry')}>Blurry</button>
      <button style={btn} onClick={() => onSetFlag('no_gps')}>No GPS</button>
      <span style={{ marginLeft: 'auto', paddingLeft: 12, fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
        {selectedCount} selected · a · u · esc
      </span>
    </div>
  )
}

// ---- main export ----
export default function ReviewTab() {
  const { selectedSessionId, setRequestedTab } = useMapStore()
  const { data: images, isLoading } = useImages(selectedSessionId)
  const { data: selectionData } = useFrameSelection(selectedSessionId)
  const setSelectionMutation = useSetFrameSelection(selectedSessionId)
  const bulkMutation = useBulkPatch(selectedSessionId)
  const [activeFlag, setActiveFlag] = useState<Image['flag'] | null>(() => {
    const f = getUrlParam('flag')
    return f ? (f as Image['flag']) : null
  })
  const [sortBy, setSortBy] = useState<'none' | 'reproj'>(() =>
    getUrlParam('sort') === 'reproj' ? 'reproj' : 'none',
  )

  // Deep-link the Review filters (e.g. ?tab=review&flag=blurry&sort=reproj).
  useEffect(() => { setUrlParam('flag', activeFlag ?? null) }, [activeFlag])
  useEffect(() => { setUrlParam('sort', sortBy === 'reproj' ? 'reproj' : null) }, [sortBy])

  if (selectedSessionId === null) {
    return (
      <EmptyState
        title="No session selected"
        description="Pick a session from the top bar, or use + Import to add a flight. Review lets you flag frames and choose what to reconstruct."
        actionLabel="Open Overview"
        onAction={() => setRequestedTab('overview')}
      />
    )
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-6" style={{ background: 'var(--bg)' }}>
        <ReconstructLoader label="Loading frames…" height={200} style={{ width: 'min(440px, 80%)' }} />
      </div>
    )
  }

  const list = images ?? []
  let filtered = activeFlag ? list.filter((img) => img.flag === activeFlag) : list
  if (sortBy === 'reproj') {
    filtered = [...filtered].sort((a, b) => {
      if (a.colmap_error_px == null && b.colmap_error_px == null) return 0
      if (a.colmap_error_px == null) return 1
      if (b.colmap_error_px == null) return -1
      return a.colmap_error_px - b.colmap_error_px
    })
  }
  const selectedSet = new Set(selectionData?.image_ids ?? [])
  const usableIds = list.filter((img) => img.usable).map((img) => img.id)

  function handleFlagClick(flag: Image['flag']) {
    setActiveFlag((prev) => (prev === flag ? null : flag))
  }

  function selectAllShown() {
    setSelectionMutation.mutate(filtered.map((img) => img.id))
  }
  function selectUsable() {
    setSelectionMutation.mutate(usableIds)
  }
  function clearSelection() {
    setSelectionMutation.mutate([])
  }

  const shownIds = filtered.map((img) => img.id)
  function markShownUsable() {
    bulkMutation.mutate({ image_ids: shownIds, usable: true })
  }
  function markShownSkip() {
    bulkMutation.mutate({ image_ids: shownIds, usable: false })
  }
  function setShownFlag(flag: Image['flag']) {
    bulkMutation.mutate({ image_ids: shownIds, flag: flag ?? undefined })
  }

  function handleSelect(id: number, checked: boolean) {
    const newIds = checked
      ? [...selectedSet, id]
      : [...selectedSet].filter((x) => x !== id)
    setSelectionMutation.mutate(newIds)
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <TabHeader
        title="Review"
        description="Flag blurry or no-GPS frames and choose which to reconstruct."
        nextTab="reconstruct"
        nextLabel="Reconstruct"
      />
      <StatsBar
        images={list}
        activeFlag={activeFlag}
        onFlagClick={handleFlagClick}
        visibleCount={filtered.length}
        selectedCount={selectedSet.size}
        sortBy={sortBy}
        onSortChange={setSortBy}
      />
      <BatchToolbar
        shownCount={filtered.length}
        usableCount={usableIds.length}
        selectedCount={selectedSet.size}
        onSelectAllShown={selectAllShown}
        onSelectUsable={selectUsable}
        onClear={clearSelection}
        onMarkUsable={markShownUsable}
        onMarkSkip={markShownSkip}
        onSetFlag={setShownFlag}
      />
      <div
        className="flex-1 overflow-y-auto p-4"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))',
          gap: 12,
          alignContent: 'start',
        }}
      >
        {filtered.map((img) => (
          <ImageCard
            key={img.id}
            img={img}
            sessionId={selectedSessionId}
            isSelected={selectedSet.has(img.id)}
            onSelect={handleSelect}
          />
        ))}
        {filtered.length === 0 && (
          <div style={{ gridColumn: '1 / -1', color: 'var(--text-muted)', textAlign: 'center', padding: '3rem 0' }}>
            No images match this filter.
          </div>
        )}
      </div>
    </div>
  )
}
