import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, patch } from '../../shared/api/client'
import { useMapStore } from '../../shared/stores/mapStore'
import type { Image } from '../../types/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ---- inline hook ----
function useImages(sessionId: number | null) {
  return useQuery<Image[]>({
    queryKey: ['images', sessionId],
    queryFn: () => get<Image[]>(`/images?session_id=${sessionId}`),
    enabled: sessionId !== null,
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
    // thumb_path is relative to the project root, e.g. "processed\1\thumbs\frame_00001.jpg"
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
}

function StatsBar({ images, activeFlag, onFlagClick, visibleCount }: StatsBarProps) {
  const counts: Record<Image['flag'], number> = {
    good: 0, blurry: 0, no_gps: 0, dark: 0, bright: 0,
  }
  for (const img of images) counts[img.flag]++

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
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)',
            fontSize: 11,
            fontFamily: 'inherit',
            padding: 0,
            marginLeft: -8,
          }}
        >
          ✕ clear
        </button>
      )}
    </div>
  )
}

// ---- image card ----
interface CardProps {
  img: Image
  sessionId: number
}

function ImageCard({ img, sessionId }: CardProps) {
  const qc = useQueryClient()

  const flagMutation = useMutation({
    mutationFn: ({ id, flag }: { id: number; flag: string }) =>
      patch<Image>(`/images/${id}`, { flag }),

    // optimistic update
    onMutate: async ({ id, flag }) => {
      await qc.cancelQueries({ queryKey: ['images', sessionId] })
      const previous = qc.getQueryData<Image[]>(['images', sessionId])
      qc.setQueryData<Image[]>(['images', sessionId], (old) =>
        old?.map((item) => (item.id === id ? { ...item, flag: flag as Image['flag'] } : item))
      )
      return { previous }
    },

    onError: (_err, _vars, context) => {
      if (context?.previous) {
        qc.setQueryData(['images', sessionId], context.previous)
      }
    },

    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['images', sessionId] })
    },
  })

  const badge = FLAG_BADGE[img.flag]

  return (
    <div
      className="flex flex-col rounded overflow-hidden"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
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
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={(e) => {
              // fallback to initials on load error
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
        onClick={() =>
          flagMutation.mutate({ id: img.id, flag: nextFlag(img.flag) })
        }
        title="Click to cycle flag"
        disabled={flagMutation.isPending}
        style={{
          position: 'absolute',
          top: 6,
          right: 6,
          padding: '2px 7px',
          borderRadius: 4,
          fontSize: 11,
          fontWeight: 600,
          border: 'none',
          cursor: 'pointer',
          background: badge.bg,
          color: badge.text,
          opacity: flagMutation.isPending ? 0.6 : 1,
          fontFamily: 'inherit',
        }}
      >
        {badge.label}
      </button>

      {/* filename */}
      <div
        className="px-2 py-1.5 text-xs truncate"
        style={{ color: 'var(--text-muted)' }}
        title={img.filename}
      >
        {img.filename}
      </div>
    </div>
  )
}

// ---- main export ----
export default function ReviewTab() {
  const { selectedSessionId } = useMapStore()
  const { data: images, isLoading } = useImages(selectedSessionId)
  const [activeFlag, setActiveFlag] = useState<Image['flag'] | null>(null)

  if (selectedSessionId === null) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ color: 'var(--text-muted)' }}
      >
        Select a session first
      </div>
    )
  }

  if (isLoading) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ color: 'var(--text-muted)' }}
      >
        Loading images…
      </div>
    )
  }

  const list = images ?? []
  const filtered = activeFlag ? list.filter((img) => img.flag === activeFlag) : list

  function handleFlagClick(flag: Image['flag']) {
    setActiveFlag((prev) => (prev === flag ? null : flag))
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <StatsBar
        images={list}
        activeFlag={activeFlag}
        onFlagClick={handleFlagClick}
        visibleCount={filtered.length}
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
          <ImageCard key={img.id} img={img} sessionId={selectedSessionId} />
        ))}
        {filtered.length === 0 && (
          <div
            style={{
              gridColumn: '1 / -1',
              color: 'var(--text-muted)',
              textAlign: 'center',
              padding: '3rem 0',
            }}
          >
            No images match this filter.
          </div>
        )}
      </div>
    </div>
  )
}
