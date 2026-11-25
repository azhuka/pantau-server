import { ref } from 'vue'

const toasts = ref([])
let nextToastId = 1

function pushToast(message, type = 'info', duration = 3500) {
  const id = nextToastId++
  toasts.value.push({ id, message: String(message || ''), type })
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration)
  }
  return id
}

function dismissToast(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    dismiss: dismissToast,
    info: (msg, dur) => pushToast(msg, 'info', dur),
    success: (msg, dur) => pushToast(msg, 'success', dur),
    warning: (msg, dur) => pushToast(msg, 'warning', dur),
    error: (msg, dur) => pushToast(msg, 'error', dur ?? 4500),
  }
}

const confirmState = ref({
  isOpen: false,
  title: 'Confirm Action',
  message: '',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  variant: 'primary',
  requirePassword: false,
  passwordLabel: 'Account Password',
  passwordPlaceholder: 'Enter your password to confirm',
})

let activeResolve = null

export function confirmAction(opts = {}) {
  return new Promise((resolve) => {
    activeResolve = resolve
    confirmState.value = {
      isOpen: true,
      title: opts.title || 'Confirm Action',
      message: opts.message || '',
      confirmText: opts.confirmText || 'Confirm',
      cancelText: opts.cancelText || 'Cancel',
      variant: opts.variant || 'primary',
      requirePassword: Boolean(opts.requirePassword),
      passwordLabel: opts.passwordLabel || 'Account Password',
      passwordPlaceholder: opts.passwordPlaceholder || 'Enter your password to confirm',
    }
  })
}

export function resolveConfirm(result) {
  confirmState.value.isOpen = false
  const fn = activeResolve
  activeResolve = null
  if (fn) fn(result)
}

export function useConfirmState() {
  return confirmState
}
