import { create } from 'zustand'

export type ToastType = 'success' | 'error' | 'info'
export interface Toast { id: string; message: string; type: ToastType }

interface ToastState {
  toasts: Toast[]
  addToast: (message: string, type?: ToastType) => void
  dismissToast: (id: string) => void
}

export const useToast = create<ToastState>((set) => ({
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = crypto.randomUUID()
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))
