import { useState, useEffect, useRef, useCallback } from 'react'
import { useImportSession } from '../../shared/api/mutations'
import { useMapStore } from '../../shared/stores/mapStore'
import { Button } from '../../shared/components/Button'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type HealthStatus = 'checking' | 'ok' | 'down'

function useBackendHealth(enabled: boolean): HealthStatus {
  const [status, setStatus] = useState<HealthStatus>('checking')

  const check = useCallback(async (signal: AbortSignal) => {
    try {
      const res = await fetch(`${BASE_URL}/health`, { signal })
      setStatus(res.ok ? 'ok' : 'down')
    } catch {
      if (!signal.aborted) setStatus('down')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()

    queueMicrotask(() => setStatus('checking'))
    const initialCheck = window.setTimeout(() => check(controller.signal), 0)
    // Re-poll every 5 s while the modal is open so it auto-recovers
    const interval = setInterval(() => check(controller.signal), 5_000)
    return () => {
      controller.abort()
      window.clearTimeout(initialCheck)
      clearInterval(interval)
    }
  }, [enabled, check])

  return status
}

interface ImportModalProps {
  open: boolean
  onClose: () => void
}

export default function ImportModal({ open, onClose }: ImportModalProps) {
  const [name, setName] = useState('')
  const [folderPath, setFolderPath] = useState('')
  const { mutate, isPending, isImporting, progress, data: importedSession, isError, error, reset } = useImportSession()
  const { setSession } = useMapStore()
  const nameRef = useRef<HTMLInputElement>(null)
  const backendStatus = useBackendHealth(open)

  // Auto-focus name input when modal opens
  useEffect(() => {
    if (open) {
      setTimeout(() => nameRef.current?.focus(), 50)
    }
  }, [open])

  // When the background import finishes successfully, switch session and close
  useEffect(() => {
    if (!isImporting && importedSession && progress?.status === 'done') {
      setSession(importedSession.id)
      handleClose()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isImporting, progress?.status])

  // ESC key closes modal (unless import is in progress)
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isImporting && !isPending) handleClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isImporting, isPending])

  function handleClose() {
    if (isImporting || isPending) return
    setName('')
    setFolderPath('')
    reset()
    onClose()
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !folderPath.trim()) return
    mutate({ name: name.trim(), folder_path: folderPath.trim() })
  }

  const progressPct =
    progress && progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : progress?.status === 'running'
      ? 5          // show a sliver while total hasn't been computed yet
      : 0

  const isBusy = isPending || isImporting
  const backendDown = backendStatus === 'down'
  const errorMessage = isError
    ? (error as Error)?.message ?? 'Import failed'
    : progress?.status === 'error'
    ? 'Import pipeline failed on the server'
    : null

  if (!open) return null

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Import Session"
      onClick={(e) => { if (e.target === e.currentTarget && !isBusy) handleClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      {/* Dialog box */}
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          width: 440,
          maxWidth: 'calc(100vw - 32px)',
          padding: '24px 28px',
          boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
          position: 'relative',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
          <h2 className="text-base font-semibold" style={{ color: 'var(--text)', margin: 0 }}>
            Import Session
          </h2>
          {!isBusy && (
            <button
              onClick={handleClose}
              aria-label="Close"
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, padding: 4,
              }}
            >
              ✕
            </button>
          )}
        </div>

        {/* Backend health warning */}
        {backendStatus !== 'ok' && (
          <div
            className="text-xs rounded"
            style={{
              padding: '8px 12px',
              marginBottom: 16,
              background: backendDown
                ? 'rgba(248,81,73,0.10)'
                : 'rgba(139,148,158,0.10)',
              border: `1px solid ${backendDown ? 'rgba(248,81,73,0.35)' : 'rgba(139,148,158,0.3)'}`,
              color: backendDown ? 'var(--danger, #f85149)' : 'var(--text-muted)',
            }}
          >
            {backendDown ? (
              <>
                <strong>Backend is not running.</strong> Start it with:
                <code
                  style={{
                    display: 'block',
                    marginTop: 5,
                    padding: '4px 8px',
                    background: 'rgba(0,0,0,0.25)',
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    fontSize: 11,
                    userSelect: 'all',
                  }}
                >
                  python -m uvicorn backend.main:app --reload --port 8000
                </code>
              </>
            ) : (
              'Checking backend…'
            )}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label
              htmlFor="import-name"
              className="text-xs font-medium block"
              style={{ color: 'var(--text-muted)', marginBottom: 6 }}
            >
              Session name
            </label>
            <input
              id="import-name"
              ref={nameRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Field A — 2026-05-02"
              disabled={isBusy}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 12px',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: 'var(--text)',
                fontSize: 13,
                fontFamily: 'inherit',
                outline: 'none',
                opacity: isBusy ? 0.6 : 1,
              }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label
              htmlFor="import-folder"
              className="text-xs font-medium block"
              style={{ color: 'var(--text-muted)', marginBottom: 6 }}
            >
              Path inside imports/ folder
            </label>
            <input
              id="import-folder"
              type="text"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="e.g. 2026-05-02-field-a"
              disabled={isBusy}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 12px',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: 'var(--text)',
                fontSize: 13,
                fontFamily: 'inherit',
                outline: 'none',
                opacity: isBusy ? 0.6 : 1,
              }}
            />
            <p className="text-xs" style={{ color: 'var(--text-muted)', marginTop: 5 }}>
              Relative path inside the server's imports/ folder — copy your JPEG files there first.
            </p>
          </div>

          {/* Progress section */}
          {isImporting && progress && (
            <div style={{ marginBottom: 20 }}>
              <div className="flex justify-between text-xs" style={{ color: 'var(--text-muted)', marginBottom: 6 }}>
                <span>
                  {progress.status === 'running'
                    ? `Processing… ${progress.processed} / ${progress.total} images`
                    : progress.status === 'done'
                    ? 'Complete!'
                    : 'Starting…'}
                </span>
                <span>{progressPct}%</span>
              </div>
              <div
                style={{
                  height: 6, borderRadius: 3,
                  background: 'var(--border)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${progressPct}%`,
                    background: 'var(--accent)',
                    borderRadius: 3,
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
            </div>
          )}

          {/* Error */}
          {errorMessage && (
            <div
              className="text-xs rounded"
              style={{
                padding: '8px 12px', marginBottom: 16,
                background: 'rgba(248,81,73,0.12)',
                border: '1px solid rgba(248,81,73,0.4)',
                color: 'var(--danger, #f85149)',
              }}
            >
              {errorMessage}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 justify-end">
            {!isBusy && (
              <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
                Cancel
              </Button>
            )}
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={isBusy || backendDown || !name.trim() || !folderPath.trim()}
            >
              {isPending ? 'Creating…' : isImporting ? 'Importing…' : 'Import'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
