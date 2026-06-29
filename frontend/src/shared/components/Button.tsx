import React, { useState } from 'react';

type ButtonVariant = 'primary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

interface VariantStyle {
  bg: string;
  hoverBg: string;
  color: string;
  border: string;
}

const variantStyles: Record<ButtonVariant, VariantStyle> = {
  primary: {
    bg: 'var(--grad-splat)',
    hoverBg: 'var(--grad-splat-hover)',
    color: 'var(--on-accent)',
    border: '1px solid var(--accent-hover)',
  },
  ghost: {
    bg: 'var(--surface)',
    hoverBg: 'var(--surface-2)',
    color: 'var(--text)',
    border: '1px solid var(--border-strong)',
  },
  danger: {
    bg: 'transparent',
    hoverBg: 'var(--danger-soft)',
    color: 'var(--danger-accent)',
    border: '1px solid var(--danger-accent)',
  },
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'text-xs px-3 py-1',
  md: 'text-sm px-4 py-2',
};

export function Button({
  variant = 'primary',
  size = 'md',
  disabled,
  className = '',
  children,
  ...props
}: ButtonProps) {
  const [hover, setHover] = useState(false);
  const v = variantStyles[variant];
  const lifted = !disabled && hover;
  return (
    <button
      disabled={disabled}
      className={`font-medium transition-colors duration-150 active:scale-[0.98] ${sizeClasses[size]} ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} ${className}`}
      style={{
        background: lifted ? v.hoverBg : v.bg,
        color: v.color,
        border: v.border,
        borderRadius: 'var(--edge)',
        fontFamily: 'var(--font-display)',
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...props}
    >
      {children}
    </button>
  );
}

export default Button;
