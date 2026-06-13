import type { CSSProperties } from 'react'

interface SkeletonProps {
  width?: number | string
  height?: number | string
  radius?: number | string
  className?: string
  style?: CSSProperties
}

/** Base skeleton block — a warm `--surface-2` rectangle that pulses. */
export function Skeleton({
  width = '100%',
  height = 12,
  radius = 'var(--radius-sm)',
  className = '',
  style,
}: SkeletonProps) {
  return (
    <div
      className={`fm-skeleton ${className}`}
      style={{ width, height, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  )
}

/** A few skeleton text lines; the last one is shorter by default. */
export function SkeletonText({
  lines = 3,
  gap = 9,
  lastWidth = '70%',
  style,
}: {
  lines?: number
  gap?: number
  lastWidth?: string
  style?: CSSProperties
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap, ...style }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height={9} width={i === lines - 1 ? lastWidth : '100%'} />
      ))}
    </div>
  )
}

/** Card-shaped skeleton matching the Panel surface. */
export function SkeletonCard({ style }: { style?: CSSProperties }) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 16px',
        ...style,
      }}
    >
      <Skeleton width="50%" height={11} />
      <div style={{ height: 10 }} />
      <SkeletonText lines={2} />
    </div>
  )
}

/** List-row skeleton: avatar block + two text lines + a trailing pill. */
export function SkeletonRow({ style }: { style?: CSSProperties }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 14px',
        ...style,
      }}
    >
      <Skeleton width={36} height={36} radius="var(--radius-md)" />
      <div style={{ flex: 1 }}>
        <Skeleton width="40%" height={10} />
        <div style={{ height: 8 }} />
        <Skeleton width="65%" height={9} />
      </div>
      <Skeleton width={52} height={20} radius="999px" />
    </div>
  )
}
