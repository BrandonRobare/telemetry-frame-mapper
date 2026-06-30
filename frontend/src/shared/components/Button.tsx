import React, { forwardRef, useState } from 'react';

type ButtonVariant = 'primary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a pending state while preserving the original accessible label. */
  loading?: boolean;
  loadingLabel?: string;
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
  sm: 'px-3 py-1',
  md: 'px-4 py-2',
};

const sizeStyles: Record<ButtonSize, React.CSSProperties> = {
  sm: { fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)' },
  md: { fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)' },
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    disabled,
    loading = false,
    loadingLabel = 'Loading…',
    className = '',
    children,
    style,
    ...props
  },
  ref,
) {
  const [hover, setHover] = useState(false);
  const v = variantStyles[variant];
  const isDisabled = disabled || loading;
  const lifted = !isDisabled && hover;
  return (
    <button
      ref={ref}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      aria-label={loading && typeof children === 'string' ? children : props['aria-label']}
      className={`inline-flex items-center justify-center gap-2 font-medium transition-colors duration-150 active:scale-[0.98] ${sizeClasses[size]} ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} ${className}`}
      style={{
        background: lifted ? v.hoverBg : v.bg,
        color: v.color,
        border: v.border,
        borderRadius: 'var(--edge)',
        fontFamily: 'var(--font-display)',
        ...sizeStyles[size],
        ...style,
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      {...props}
    >
      {loading && (
        <span
          aria-hidden="true"
          style={{
            width: '1em',
            height: '1em',
            border: '2px solid currentColor',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            display: 'inline-block',
            animation: 'tg-button-spin 0.75s linear infinite',
          }}
        />
      )}
      <span>{loading ? loadingLabel : children}</span>
    </button>
  );
});

export default Button;
