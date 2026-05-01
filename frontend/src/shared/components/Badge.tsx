import React from 'react';

type BadgeColor = 'green' | 'amber' | 'red' | 'blue' | 'muted';

interface BadgeProps {
  color: BadgeColor;
  children: React.ReactNode;
}

const colorVarMap: Record<BadgeColor, string> = {
  green: 'var(--success)',
  amber: 'var(--warning)',
  red: 'var(--danger)',
  blue: 'var(--accent)',
  muted: 'var(--text-muted)',
};

// Fallback hex values for background at 15% opacity
const colorBgMap: Record<BadgeColor, string> = {
  green: 'rgba(34, 197, 94, 0.15)',
  amber: 'rgba(251, 191, 36, 0.15)',
  red: 'rgba(239, 68, 68, 0.15)',
  blue: 'rgba(99, 102, 241, 0.15)',
  muted: 'rgba(156, 163, 175, 0.15)',
};

export function Badge({ color, children }: BadgeProps) {
  return (
    <span
      className="rounded-full text-xs px-2 py-0.5 inline-flex font-medium"
      style={{
        color: colorVarMap[color],
        background: colorBgMap[color],
      }}
    >
      {children}
    </span>
  );
}

export default Badge;
