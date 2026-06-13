import React from 'react';

type BadgeColor = 'sage' | 'amber' | 'red' | 'terracotta' | 'tan' | 'muted';

interface BadgeProps {
  color: BadgeColor;
  children: React.ReactNode;
}

// Warm-light token pairs: readable text on a soft tint of the same family.
const colorMap: Record<BadgeColor, { text: string; bg: string }> = {
  sage:       { text: 'var(--success)', bg: 'var(--success-soft)' },
  amber:      { text: 'var(--warning)', bg: 'var(--warning-soft)' },
  red:        { text: 'var(--danger)',  bg: 'var(--danger-soft)' },
  terracotta: { text: 'var(--accent-strong)', bg: 'var(--accent-soft)' },
  tan:        { text: 'var(--tan-text)', bg: 'var(--tan-soft)' },
  muted:      { text: 'var(--text-muted)', bg: 'var(--surface-2)' },
};

export function Badge({ color, children }: BadgeProps) {
  const c = colorMap[color];
  return (
    <span
      className="rounded-full text-xs px-2 py-0.5 inline-flex font-medium"
      style={{ color: c.text, background: c.bg }}
    >
      {children}
    </span>
  );
}

export default Badge;
