import React from 'react';

interface PanelProps {
  children: React.ReactNode;
  className?: string;
}

export function Panel({ children, className = '' }: PanelProps) {
  return (
    <div
      className={className}
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
      }}
    >
      {children}
    </div>
  );
}

export default Panel;
