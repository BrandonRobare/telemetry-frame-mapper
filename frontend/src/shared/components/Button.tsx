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

/* minHeight/minWidth mirror the app-wide WCAG 2.2 SC 2.5.8 floor in index.css.
   Kept here as well so the contract travels with the component and is visible
   to anyone reading it — `sm` used to be px-3 py-1 with no minimum at all. */
const TARGET_FLOOR = { minHeight: 24, minWidth: 24 } as const;

const sizeStyles: Record<ButtonSize, React.CSSProperties> = {
  sm: { fontSize: 'var(--text-xs)', lineHeight: 'var(--leading-normal)', ...TARGET_FLOOR },
  md: { fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-normal)', ...TARGET_FLOOR },
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    disabled,
    loading = false,
    loadingLabel = 'Loading…',
    className = '',
    style,
    onMouseEnter,
    onMouseLeave,
    children,
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
      onMouseEnter={(event) => {
        setHover(true);
        onMouseEnter?.(event);
      }}
      onMouseLeave={(event) => {
        setHover(false);
        onMouseLeave?.(event);
      }}
      {...props}
    >
      {loading && <span aria-hidden="true" className="tg-button-spinner" />}
      <span>{loading ? loadingLabel : children}</span>
    </button>
  );
});

export default Button;
