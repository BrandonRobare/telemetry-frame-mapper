import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface AdvancedDisclosureProps {
  children: React.ReactNode
  label?: string
}

export function AdvancedDisclosure({ children, label = 'Advanced' }: AdvancedDisclosureProps) {
  const [open, setOpen] = useState(false)

  return (
    <div
      style={{
        borderTop: '1px solid var(--border)',
        marginTop: 8,
        paddingTop: 8,
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 cursor-pointer border-none bg-transparent"
        style={{
          padding: '4px 0',
          fontSize: 12,
          color: 'var(--text-muted)',
          fontFamily: 'inherit',
          transition: 'color var(--dur) var(--ease)',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--text)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
        aria-expanded={open}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="currentColor"
          style={{
            transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform var(--dur) var(--ease)',
            flexShrink: 0,
          }}
          aria-hidden="true"
        >
          <path d="M4 2.5l4 3.5-4 3.5V2.5z" />
        </svg>
        {label}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="advanced-content"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 16 }}>
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default AdvancedDisclosure
