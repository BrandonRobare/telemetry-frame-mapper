import React from 'react';
import GlassSurface from './GlassSurface';

interface PanelProps {
  children: React.ReactNode;
  className?: string;
  /** 'solid' (default) keeps the original flat surface; 'glass' opts into the
      translucent Terrain-glass treatment. */
  variant?: 'solid' | 'glass';
  style?: React.CSSProperties;
}

export function Panel({ children, className = '', variant = 'solid', style }: PanelProps) {
  if (variant === 'glass') {
    return (
      <GlassSurface
        interactive={false}
        refraction={false}
        radius={0}
        className={className}
        style={style}
      >
        {children}
      </GlassSurface>
    );
  }

  return (
    <div
      className={className}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        transition: 'border-color var(--dur) var(--ease)',
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export default Panel;
