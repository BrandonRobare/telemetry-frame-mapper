import { useQuery } from '@tanstack/react-query'
import { get } from '../../shared/api/client'

interface ShareViewerPayload {
  reconstruction_id: number
  session_id: number
  status: string
  frames_used: number
  frames_registered: number | null
  gaussian_count: number | null
  psnr: number | null
  ssim: number | null
  artifacts: {
    pointcloud: string | null
    mesh_glb: string | null
    mesh_obj: string | null
  }
  generated_at: number
}

function getToken(): string {
  // URL format: /view/share/<token>
  const parts = window.location.pathname.split('/')
  const idx = parts.indexOf('share')
  return idx >= 0 ? parts.slice(idx + 1).join('/') : ''
}

export default function ShareViewer() {
  const token = getToken()

  const { data, isLoading, error } = useQuery<ShareViewerPayload>({
    queryKey: ['share', token],
    queryFn: () => get<ShareViewerPayload>(`/share/token/${token}`),
    enabled: !!token,
  })

  if (!token) {
    return <ShareError status={400} message="No share token in URL" />
  }

  if (isLoading) {
    return (
      <div
        className="flex-1 flex items-center justify-center"
        style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-muted)' }}
      >
        <div className="flex flex-col items-center gap-3">
          <div
            className="tg-indeterminate"
            style={{
              width: 40,
              height: 4,
              background: 'var(--accent)',
              borderRadius: 2,
            }}
          />
          <span className="text-sm">Loading shared reconstruction…</span>
        </div>
      </div>
    )
  }

  if (error) {
    const msg = error instanceof Error ? error.message : 'Failed to load share'
    return <ShareError status={403} message={msg} />
  }

  if (!data || data.status !== 'complete') {
    return <ShareError status={410} message="Reconstruction is not available for viewing" />
  }

  return (
    <div
      className="flex flex-col"
      style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}
    >
      {/* Header banner */}
      <header
        className="shrink-0 flex items-center justify-between px-6"
        style={{
          height: 44,
          background: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <span
          className="text-sm font-semibold"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Telemetry Frame Mapper · Shared View
        </span>
      </header>

      {/* Metadata panel */}
      <main
        className="flex-1 p-6 mx-auto flex flex-col gap-6"
        style={{ maxWidth: 640, width: '100%' }}
      >
        <section
          className="p-5 flex flex-col gap-3"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ margin: 0 }}>
            Reconstruction #{data.reconstruction_id}
          </h2>

          <dl
            className="grid gap-x-8 gap-y-2 text-sm"
            style={{ gridTemplateColumns: 'auto 1fr' }}
          >
            <dt style={{ color: 'var(--text-muted)' }}>Frames used</dt>
            <dd style={{ margin: 0 }}>{data.frames_used}</dd>

            <dt style={{ color: 'var(--text-muted)' }}>Frames registered</dt>
            <dd style={{ margin: 0 }}>{data.frames_registered ?? '—'}</dd>

            <dt style={{ color: 'var(--text-muted)' }}>Gaussian count</dt>
            <dd style={{ margin: 0 }}>
              {data.gaussian_count != null ? data.gaussian_count.toLocaleString() : '—'}
            </dd>

            <dt style={{ color: 'var(--text-muted)' }}>PSNR</dt>
            <dd style={{ margin: 0 }}>
              {data.psnr != null ? `${data.psnr.toFixed(2)} dB` : '—'}
            </dd>

            <dt style={{ color: 'var(--text-muted)' }}>SSIM</dt>
            <dd style={{ margin: 0 }}>
              {data.ssim != null ? data.ssim.toFixed(4) : '—'}
            </dd>
          </dl>
        </section>

        {/* Download links */}
        <section
          className="p-5 flex flex-col gap-4"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-base font-semibold" style={{ margin: 0 }}>
            Available Artifacts
          </h2>

          {(Object.keys(data.artifacts) as Array<keyof typeof data.artifacts>).every(
            (k) => !data.artifacts[k]
          ) && (
            <p className="text-sm" style={{ color: 'var(--text-muted)', margin: 0 }}>
              No downloadable artifacts available for this reconstruction.
            </p>
          )}

          <div className="flex gap-2 flex-wrap">
            {data.artifacts.pointcloud && (
              <a
                href={data.artifacts.pointcloud + '?token=' + encodeURIComponent(token)}
                className="text-sm no-underline whitespace-nowrap"
                style={{
                  padding: '5px 10px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--accent-soft)',
                  border: '1px solid var(--accent-soft)',
                  color: 'var(--accent-strong)',
                }}
              >
                Download Point Cloud (LAS)
              </a>
            )}
            {data.artifacts.mesh_glb && (
              <a
                href={data.artifacts.mesh_glb + '&token=' + encodeURIComponent(token)}
                className="text-sm no-underline whitespace-nowrap"
                style={{
                  padding: '5px 10px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--accent-soft)',
                  border: '1px solid var(--accent-soft)',
                  color: 'var(--accent-strong)',
                }}
              >
                Download Mesh (GLB)
              </a>
            )}
            {data.artifacts.mesh_obj && (
              <a
                href={data.artifacts.mesh_obj + '&token=' + encodeURIComponent(token)}
                className="text-sm no-underline whitespace-nowrap"
                style={{
                  padding: '5px 10px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--accent-soft)',
                  border: '1px solid var(--accent-soft)',
                  color: 'var(--accent-strong)',
                }}
              >
                Download Mesh (OBJ)
              </a>
            )}
          </div>
        </section>

        {/* Footer */}
        <footer
          className="text-xs"
          style={{ color: 'var(--text-muted)', textAlign: 'center' }}
        >
          Generated {new Date(data.generated_at * 1000).toLocaleString()} · Read-only
          viewer · Telemetry Frame Mapper
        </footer>
      </main>
    </div>
  )
}

function ShareError({ status, message }: { status: number; message: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3"
      style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}
    >
      <div
        className="text-5xl font-bold"
        style={{ fontFamily: 'var(--font-display)', color: 'var(--text-muted)' }}
      >
        {status}
      </div>
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
        {message}
      </p>
      <a
        href="/"
        className="text-sm no-underline"
        style={{
          marginTop: 8,
          color: 'var(--accent-strong)',
        }}
      >
        Back to Telemetry Frame Mapper
      </a>
    </div>
  )
}