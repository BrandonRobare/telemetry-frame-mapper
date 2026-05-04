import { useToast } from '../hooks/useToast'

const colors: Record<string, string> = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  info: 'bg-blue-600',
}

export function ToastStack() {
  const { toasts, dismissToast } = useToast()
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-50">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`${colors[t.type]} text-white px-4 py-2 rounded shadow-lg flex items-center gap-3 text-sm`}
        >
          <span>{t.message}</span>
          <button onClick={() => dismissToast(t.id)} className="ml-auto opacity-70 hover:opacity-100">✕</button>
        </div>
      ))}
    </div>
  )
}
