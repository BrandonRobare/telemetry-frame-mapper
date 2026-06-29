import { AnimatePresence, motion } from 'framer-motion'
import { useToast } from '../hooks/useToast'
import { easeOut } from '../motion'
import { glassBackdrop } from '../motion/glassSupport'

const styleByType: Record<string, { bg: string; color: string; bar: string }> = {
  success: { bg: 'color-mix(in srgb, var(--success-soft) 76%, transparent)', color: 'var(--success)', bar: 'var(--sage)' },
  error: { bg: 'color-mix(in srgb, var(--danger-soft) 76%, transparent)', color: 'var(--danger)', bar: 'var(--danger-accent)' },
  info: { bg: 'color-mix(in srgb, var(--surface) 70%, transparent)', color: 'var(--text)', bar: 'var(--accent)' },
}

export function ToastStack() {
  const { toasts, dismissToast } = useToast()
  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50" role="status" aria-live="polite" aria-relevant="additions" style={{ maxWidth: 340 }}>
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const s = styleByType[t.type] ?? styleByType.info
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 24 }}
              transition={{ duration: 0.18, ease: easeOut }}
              className="px-4 py-2 flex items-center gap-3 text-sm"
              style={{
                background: s.bg,
                color: s.color,
                borderTop: '1px solid var(--glass-border)',
                borderRight: '1px solid var(--glass-border)',
                borderBottom: '1px solid var(--glass-border)',
                borderLeft: `3px solid ${s.bar}`,
                borderRadius: 'var(--radius-md)',
                backdropFilter: glassBackdrop(true),
                WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(1.35)',
                boxShadow: 'var(--shadow-1)',
              }}
            >
              <span style={{ flex: 1 }}>{t.message}</span>
              {t.action && (
                <button
                  onClick={() => { t.action!.onClick(); dismissToast(t.id) }}
                  className="shrink-0 cursor-pointer border-none bg-transparent"
                  style={{ color: 'inherit', fontWeight: 600, textDecoration: 'underline', textUnderlineOffset: 2, fontFamily: 'var(--font-display)' }}
                >
                  {t.action.label}
                </button>
              )}
              <button
                onClick={() => dismissToast(t.id)}
                className="shrink-0 opacity-60 hover:opacity-100 cursor-pointer border-none bg-transparent"
                style={{ color: 'inherit' }}
                aria-label="Dismiss"
              >
                ✕
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
