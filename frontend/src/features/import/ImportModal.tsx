import { useState, useEffect, useRef, useCallback } from 'react'
import { useImportSession } from '../../shared/api/mutations'
import {
  browserUploadDisplayPath,
  summarizeBrowserUpload,
  uploadBrowserImport,
  type BrowserUploadFilePlan,
  type BrowserUploadProgress,
} from '../../shared/api/browserUpload'
import { useMapStore } from '../../shared/stores/mapStore'
import { useQuickReport } from '../map/hooks/useQuickReport'
import RapidQACard from '../overview/RapidQACard'
import { Button } from '../../shared/components/Button'
import { validateImportPath } from './validateImportPath'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type HealthStatus = 'checking' | 'ok' | 'down'
type ImportMode = 'browser' | 'server-path'

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`
}

function filesToPlans(fileList: FileList | File[]): BrowserUploadFilePlan[] {
  return Array.from(fileList).map((file) => ({
    file,
    path: browserUploadDisplayPath(file),
  }))
}

interface ImportModalProps {
  open: boolean
  onClose: () => void
}

export default function ImportModal({ open, onClose }: ImportModalProps) {
  const [mode, setMode] = useState<ImportMode>('browser')
  const [name, setName] = useState('')
  const [folderPath, setFolderPath] = useState('')
  const [pathError, setPathError] = useState<string | null>(null)
  const [browserFiles, setBrowserFiles] = useState<BrowserUploadFilePlan[]>([])
  const [browserProgress, setBrowserProgress] = useState<BrowserUploadProgress | null>(null)
  const [browserError, setBrowserError] = useState<string | null>(null)
  const [isBrowserUploading, setIsBrowserUploading] = useState(false)
  const uploadAbortRef = useRef<AbortController | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { mutate, isPending, isImporting, progress, data: importedSession, isError, error, reset } = useImportSession()
  const { setSession } = useMapStore()
  const nameRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const prevFocusRef = useRef<HTMLElement | null>(null)
  const backendStatus = useBackendHealth(open)
  const lastDoneSessionRef = useRef<number | null>(null)
  const [postImportDismissed, setPostImportDismissed] = useState(false)
  const importDoneSessionId = (!isImporting && importedSession && progress?.status === 'done')
    ? importedSession.id
    : null
  const { data: quickReport } = useQuickReport(importDoneSessionId)

  // Auto-focus name input when modal opens; remember what to restore focus to.
  useEffect(() => {
    if (open) {
      prevFocusRef.current = document.activeElement as HTMLElement
      setTimeout(() => nameRef.current?.focus(), 50)
    }
  }, [open])

  // Keep Tab focus inside the dialog.
  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== 'Tab' || !dialogRef.current) return
    const nodes = dialogRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), [href], select, textarea, [tabindex]:not([tabindex="-1"])',
    )
    if (nodes.length === 0) return
    const first = nodes[0]
    const last = nodes[nodes.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }

  // When the background import finishes successfully, switch session and show QA
  useEffect(() => {
    if (!isImporting && importedSession && progress?.status === 'done') {
      // If a new import completed (different session), reset dismiss state
      if (lastDoneSessionRef.current !== importedSession.id) {
        lastDoneSessionRef.current = importedSession.id
        setPostImportDismissed(false)
      }
      setSession(importedSession.id)
      // Don't auto-close — let the user see the QA card and dismiss
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isImporting, progress?.status])

  // ESC key closes modal (unless import is in progress)
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isBusy) handleClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, isBrowserUploading, isImporting, isPending])

  const summary = summarizeBrowserUpload(browserFiles)
  const uploadPct = browserProgress && browserProgress.totalBytes > 0
    ? Math.round((browserProgress.uploadedBytes / browserProgress.totalBytes) * 100)
    : browserProgress?.status === 'importing'
      ? 100
      : 0
  const progressPct =
    progress && progress.total > 0
      ? Math.round((progress.processed / progress.total) * 100)
      : progress?.status === 'running'
        ? 5          // show a sliver while total hasn't been computed yet
        : 0

  const isBusy = isPending || isImporting || isBrowserUploading
  const backendDown = backendStatus === 'down'
  const errorMessage = browserError
    || (isError
      ? (error as Error)?.message ?? 'Import failed. Check the folder path and that the backend is running.'
      : progress?.status === 'error'
        ? progress.error || 'Import pipeline failed on the server. Check the backend logs and try again.'
        : null)

  function resetBrowserState() {
    setBrowserFiles([])
    setBrowserProgress(null)
    setBrowserError(null)
    uploadAbortRef.current = null
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function handleClose() {
    if (isBusy) return
    setName('')
    setFolderPath('')
    setPathError(null)
    resetBrowserState()
    reset()
    onClose()
    prevFocusRef.current?.focus?.()
  }

  function handleFilesSelected(fileList: FileList | File[]) {
    const plans = filesToPlans(fileList).filter((item) => /\.jpe?g$/i.test(item.path))
    setBrowserFiles(plans)
    setBrowserError(plans.length === 0 ? 'Choose one or more JPEG images to upload.' : null)
    setBrowserProgress(null)
  }

  async function handleBrowserUpload() {
    if (!name.trim() || browserFiles.length === 0) return
    const controller = new AbortController()
    uploadAbortRef.current = controller
    setBrowserError(null)
    setIsBrowserUploading(true)
    try {
      const result = await uploadBrowserImport({
        name: name.trim(),
        files: browserFiles,
        signal: controller.signal,
        onProgress: setBrowserProgress,
      })
      setSession(result.session.id)
      setIsBrowserUploading(false)
      handleClose()
    } catch (err) {
      const message = err instanceof DOMException && err.name === 'AbortError'
        ? 'Upload cancelled.'
        : err instanceof Error ? err.message : 'Upload failed.'
      setBrowserError(message)
      setIsBrowserUploading(false)
      uploadAbortRef.current = null
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (mode === 'browser') {
      void handleBrowserUpload()
      return
    }
    if (!name.trim() || !folderPath.trim()) return
    const pathProblem = validateImportPath(folderPath)
    setPathError(pathProblem)
    if (pathProblem) return
    mutate({ name: name.trim(), folder_path: folderPath.trim() })
  }

  function cancelBrowserUpload() {
    uploadAbortRef.current?.abort()
  }

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
        padding: 12,
      }}
    >
      {/* Dialog box */}
      <div
        ref={dialogRef}
        onKeyDown={trapTab}
        className="fm-import-dialog"
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border-strong)',
          borderRadius: 2,
          width: 520,
          maxWidth: '100%',
          maxHeight: 'calc(100dvh - 24px)',
          overflowY: 'auto',
          padding: '24px 28px',
          boxShadow: '0 24px 60px -20px rgba(74,52,30,0.55)',
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
              background: backendDown ? 'var(--danger-soft)' : 'var(--surface-2)',
              border: `1px solid ${backendDown ? 'var(--danger-accent)' : 'var(--border)'}`,
              color: backendDown ? 'var(--danger)' : 'var(--text-muted)',
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
                    background: 'rgba(46,42,34,0.10)',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-mono)',
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
              name="session-name"
              autoComplete="off"
              spellCheck={false}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Field A, 2026-05-02"
              disabled={isBusy}
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 12px',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text)',
                fontSize: 13,
                fontFamily: 'inherit',
                opacity: isBusy ? 0.6 : 1,
              }}
            />
          </div>

          <div className="fm-import-mode-toggle flex gap-2" style={{ marginBottom: 16 }}>
            <Button
              type="button"
              variant={mode === 'browser' ? 'primary' : 'ghost'}
              size="sm"
              disabled={isBusy}
              onClick={() => setMode('browser')}
            >
              Upload files
            </Button>
            <Button
              type="button"
              variant={mode === 'server-path' ? 'primary' : 'ghost'}
              size="sm"
              disabled={isBusy}
              onClick={() => setMode('server-path')}
            >
              Server path
            </Button>
          </div>

          {mode === 'browser' ? (
            <div style={{ marginBottom: 20 }}>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,.jpg,.jpeg"
                multiple
                // Chromium exposes directory selection via this non-standard attribute.
                {...{ webkitdirectory: '' }}
                style={{ display: 'none' }}
                onChange={(e) => { if (e.target.files) handleFilesSelected(e.target.files) }}
              />
              <div
                role="button"
                tabIndex={0}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  handleFilesSelected(e.dataTransfer.files)
                }}
                style={{
                  border: '1px dashed var(--border-strong)',
                  background: 'var(--surface-2)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 18,
                  color: 'var(--text-muted)',
                  cursor: isBusy ? 'default' : 'pointer',
                  textAlign: 'center',
                }}
              >
                <div className="text-sm" style={{ color: 'var(--text)', marginBottom: 4 }}>
                  Drop a JPEG folder or image batch here
                </div>
                <div className="text-xs">or click to choose files from your browser</div>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-muted)', marginTop: 8 }}>
                {summary.count > 0
                  ? `${summary.count} JPEG files selected (${formatBytes(summary.totalBytes)})`
                  : 'Large imports are uploaded in chunks and can be cancelled while in progress.'}
              </p>
            </div>
          ) : (
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
                name="folder-path"
                autoComplete="off"
                spellCheck={false}
                value={folderPath}
                onChange={(e) => { setFolderPath(e.target.value); setPathError(null) }}
                placeholder="e.g. 2026-05-02-field-a"
                disabled={isBusy}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  padding: '8px 12px',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text)',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  opacity: isBusy ? 0.6 : 1,
                }}
              />
              <p className="text-xs" style={{ color: 'var(--text-muted)', marginTop: 5 }}>
                Relative path inside the server's imports/ folder. Copy your JPEG files there first.
              </p>
              {pathError && (
                <p className="text-xs" style={{ color: 'var(--danger)', marginTop: 4 }}>
                  {pathError}
                </p>
              )}
            </div>
          )}

          {/* Progress section */}
          {isBrowserUploading && browserProgress && (
            <div style={{ marginBottom: 20 }}>
              <div className="flex justify-between text-xs" style={{ color: 'var(--text-muted)', marginBottom: 6 }}>
                <span>
                  {browserProgress.status === 'importing'
                    ? 'Upload complete — starting import…'
                    : `Uploading… ${formatBytes(browserProgress.uploadedBytes)} / ${formatBytes(browserProgress.totalBytes)}`}
                </span>
                <span>{uploadPct}%</span>
              </div>
              <div
                style={{
                  height: 6, borderRadius: 3,
                  background: 'var(--surface-2)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${uploadPct}%`,
                    background: 'var(--accent)',
                    borderRadius: 3,
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
            </div>
          )}

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
                  background: 'var(--surface-2)',
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
                background: 'var(--danger-soft)',
                border: '1px solid var(--danger-accent)',
                color: 'var(--danger)',
              }}
            >
              {errorMessage}
            </div>
          )}

          {/* Post-import QA card */}
          {importDoneSessionId && quickReport && !postImportDismissed && !isBusy && (
            <div style={{ marginBottom: 16 }}>
              <div className="flex items-center justify-between mb-2">
                <span
                  className="text-xs font-semibold"
                  style={{ color: 'var(--text)', fontFamily: 'var(--font-display)' }}
                >
                  Import complete — Quick QA
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setPostImportDismissed(true)
                    handleClose()
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-muted)',
                    fontSize: 14,
                    lineHeight: 1,
                    padding: '2px 4px',
                  }}
                  aria-label="Dismiss and close"
                >
                  ✕
                </button>
              </div>
              <RapidQACard report={quickReport} compact />
            </div>
          )}

          {/* Actions */}
          <div className="fm-import-actions flex gap-2 justify-end">
            {isBrowserUploading ? (
              <Button type="button" variant="ghost" size="sm" onClick={cancelBrowserUpload}>
                Cancel upload
              </Button>
            ) : !isBusy && (
              <Button type="button" variant="ghost" size="sm" onClick={handleClose}>
                Cancel
              </Button>
            )}
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={
                isBusy
                || backendDown
                || !name.trim()
                || (mode === 'browser' ? browserFiles.length === 0 : !folderPath.trim())
              }
            >
              {isBrowserUploading
                ? 'Uploading…'
                : isPending
                  ? 'Creating…'
                  : isImporting
                    ? 'Importing…'
                    : mode === 'browser' ? 'Upload & Import' : 'Import'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
