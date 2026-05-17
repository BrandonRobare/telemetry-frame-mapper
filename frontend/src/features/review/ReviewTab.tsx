import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
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

// ---- flag cycling ----
const FLAG_CYCLE: Image['flag'][] = ['good', 'blurry', 'no_gps']

function nextFlag(current: Image['flag']): Image['flag'] {
  const idx = FLAG_CYCLE.indexOf(current)
  if (idx === -1) return 'good'
  return FLAG_CYCLE[(idx + 1) % FLAG_CYCLE.length]
}

// ---- badge colour ----
const FLAG_BADGE: Record<Image['flag'], { bg: string; text: string; label: string }> = {
  good:   { bg: '#166534', text: '#bbf7d0', label: 'Good' },
  blurry: { bg: '#78350f', text: '#fde68a', label: 'Blurry' },
  no_gps: { bg: '#1e3a5f', text: '#bfdbfe', label: 'No GPS' },
  dark:   { bg: '#374151', text: '#d1d5db', label: 'Dark' },
  bright: { bg: '#374151', text: '#d1d5db', label: 'Bright' },
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
}

function StatsBar({ images, activeFlag, onFlagClick, visibleCount, selectedCount }: StatsBarProps) {
  const counts: Record<Image['flag'], number> = {
    good: 0, blurry: 0, no_gps: 0, dark: 0, bright: 0,
  }
  for (const img of images) counts[img.flag]++
  const usableCount = images.filter((img) => img.usable).length

  const items: { label: string; flag: Image['flag']; count: number; color: string }[] = [
    { label: 'Good',   flag: 'good',   count: counts.good,   color: '#4ade80' },
    { label: 'Blurry', flag: 'blurry', count: counts.blurry, color: '#fbbf24' },
    { label: 'No GPS', flag: 'no_gps', count: counts.no_gps, color: '#60a5fa' },
    { label: 'Dark',   flag: 'dark',   count: counts.dark,   color: '#9ca3af' },
    { label: 'Bright', flag: 'bright', count: counts.bright, color: '#9ca3af' },
  ]

  return (
    <div
      className="flex gap-6 items-center shrink-0 px-5 py-3 text-sm"
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}
    >
      <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
        {activeFlag ? `${visibleCount} / ${images.length}` : `${images.length}`} images
      </span>
      {items.map(({ label, flag, count, color }) => {
        const active = activeFlag === flag
        return (
          <button
            key={flag}
            onClick={() => onFlagClick(flag)}
            className="flex items-center gap-1.5"
            style={{
              background: active ? 'var(--border)' : 'none',
              border: 'none',
              borderRadius: 4,
              padding: active ? '2px 6px' : '2px 0',
              cursor: 'pointer',
              fontFamily: 'inherit',
              fontSize: 'inherit',
              outline: 'none',
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
      <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
        {selectedCount > 0 && (
          <span style={{ color: '#c4b5fd', fontWeight: 600, marginRight: 8 }}>
            {selectedCount} selected for reconstruction
          </span>
        )}
        <span style={{ color: '#86efac', fontWeight: 600 }}>{usableCount}</span>
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
      className="flex flex-col rounded overflow-hidden"
      style={{
        background: 'var(--surface)',
        border: isSelected
          ? '1px solid #a78bfa'
          : img.usable ? '1px solid var(--border)' : '1px solid #7f1d1d',
        position: 'relative',
        minHeight: 152,
      }}
    >
      {/* thumbnail */}
      <div
        className="flex items-center justify-center text-sm font-bold"
        style={{ height: 120, background: 'var(--bg)', overflow: 'hidden' }}
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

      {/* flag badge — top-right, clickable */}
      <button
        onClick={() => flagMutation.mutate({ id: img.id, flag: nextFlag(img.flag) })}
        title="Click to cycle flag"
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
            <span title="Brightness (mean pixel 0–255)">☀ {img.brightness_score.toFixed(0)}</span>
          )}
        </div>
      </div>

      {/* reconstruction selection checkbox */}
      <label
        style={{
          display: 'flex', alignItems: 'center', gap: 5,
          margin: '4px 8px 0', cursor: 'pointer',
          fontSize: 11, color: isSelected ? '#c4b5fd' : 'var(--text-muted)',
          fontFamily: 'inherit',
        }}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(img.id, e.target.checked)}
          style={{ accentColor: '#a78bfa', cursor: 'pointer' }}
        />
        For reconstruction
      </label>

      {/* usable toggle */}
      <button
        onClick={() => usableMutation.mutate({ id: img.id, usable: !img.usable })}
        disabled={usableMutation.isPending}
        style={{
          margin: '4px 8px 8px', padding: '3px 0', borderRadius: 4,
          fontSize: 11, fontWeight: 600, border: 'none', cursor: 'pointer',
          background: img.usable ? '#14532d' : '#450a0a',
          color: img.usable ? '#86efac' : '#fca5a5',
          opacity: usableMutation.isPending ? 0.6 : 1, fontFamily: 'inherit',
          width: 'calc(100% - 16px)',
        }}
        title={img.usable ? 'Mark as skip' : 'Mark as usable'}
      >
        {img.usable ? '✓ Usable' : '✗ Skip'}
      </button>
    </div>
  )
}

// ---- main export ----
export default function ReviewTab() {
  const { selectedSessionId } = useMapStore()
  const { data: images, isLoading } = useImages(selectedSessionId)
  const { data: selectionData } = useFrameSelection(selectedSessionId)
  const setSelectionMutation = useSetFrameSelection(selectedSessionId)
  const [activeFlag, setActiveFlag] = useState<Image['flag'] | null>(null)

  if (selectedSessionId === null) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Select a session first
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        Loading images…
      </div>
    )
  }

  const list = images ?? []
  const filtered = activeFlag ? list.filter((img) => img.flag === activeFlag) : list
  const selectedSet = new Set(selectionData?.image_ids ?? [])

  function handleFlagClick(flag: Image['flag']) {
    setActiveFlag((prev) => (prev === flag ? null : flag))
  }

  function handleSelect(id: number, checked: boolean) {
    const newIds = checked
      ? [...selectedSet, id]
      : [...selectedSet].filter((x) => x !== id)
    setSelectionMutation.mutate(newIds)
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <StatsBar
        images={list}
        activeFlag={activeFlag}
        onFlagClick={handleFlagClick}
        visibleCount={filtered.length}
        selectedCount={selectedSet.size}
      />
      <div
        className="flex-1 overflow-y-auto p-4"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
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
