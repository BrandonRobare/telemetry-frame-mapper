import { AnimatePresence, motion } from 'framer-motion'
import { useToast } from '../hooks/useToast'
import { easeOut } from '../motion'

const styleByType: Record<string, { bg: string; color: string; bar: string }> = {
  success: { bg: 'var(--success-soft)', color: 'var(--success)', bar: 'var(--sage)' },
  error: { bg: 'var(--danger-soft)', color: 'var(--danger)', bar: 'var(--danger-accent)' },
  info: { bg: 'var(--surface)', color: 'var(--text)', bar: 'var(--accent)' },
}

export function ToastStack() {
  const { toasts, dismissToast } = useToast()
  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50" style={{ maxWidth: 340 }}>
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
                border: '1px solid var(--border)',
                borderLeft: `3px solid ${s.bar}`,
                borderRadius: 'var(--radius-md)',
              }}
            >
              <span>{t.message}</span>
              <button
                onClick={() => dismissToast(t.id)}
                className="ml-auto opacity-60 hover:opacity-100 cursor-pointer border-none bg-transparent"
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
