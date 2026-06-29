import { create } from 'zustand'

export type ToastType = 'success' | 'error' | 'info'
export interface ToastAction { label: string; onClick: () => void }
export interface Toast { id: string; message: string; type: ToastType; action?: ToastAction }

interface ToastState {
  toasts: Toast[]
  addToast: (message: string, type?: ToastType, action?: ToastAction) => void
  dismissToast: (id: string) => void
}

export const useToast = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type = 'info', action) => {
    const id = crypto.randomUUID()
    set((s) => ({ toasts: [...s.toasts, { id, message, type, action }] }))
    // Actioned toasts (e.g. Undo) linger a little longer so they can be clicked.
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), action ? 6000 : 4000)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
