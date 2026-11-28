import { ref } from 'vue'

const toasts = ref([])
let nextToastId = 1
const timers = new Map()

function startTimer(id, ms) {
  clearTimer(id)
  if (!ms || ms <= 0) return
  const item = toasts.value.find(t => t.id === id)
  if (!item) return
  item.startedAt = Date.now()
  item.remainingMs = ms
  item.paused = false
  timers.set(id, setTimeout(() => dismissToast(id), ms))
}

function clearTimer(id) {
  const t = timers.get(id)
  if (t) {
    clearTimeout(t)
    timers.delete(id)
  }
}

export function pauseToast(id) {
  const item = toasts.value.find(t => t.id === id)
  if (!item || item.paused) return
  clearTimer(id)
  const elapsed = Date.now() - (item.startedAt || Date.now())
  item.remainingMs = Math.max(600, (item.remainingMs || 5000) - elapsed)
  item.paused = true
}

export function resumeToast(id) {
  const item = toasts.value.find(t => t.id === id)
  if (!item || !item.paused) return
  startTimer(id, item.remainingMs || 3000)
}

function defaultTitle(type) {
  if (type === 'success') return 'Success'
  if (type === 'error') return 'Error'
  if (type === 'warning') return 'Warning'
  return 'Notification'
}

function pushToast(optsOrMsg, type = 'info', duration = 5000) {
  const isObj = typeof optsOrMsg === 'object' && optsOrMsg !== null && !(optsOrMsg instanceof Error) && !Array.isArray(optsOrMsg) && ('message' in optsOrMsg || 'title' in optsOrMsg || 'type' in optsOrMsg)
  const tType = isObj ? (optsOrMsg.type || 'info') : type
  const dur = isObj ? (optsOrMsg.duration ?? 5500) : duration
  const id = nextToastId++
  const rawMsg = isObj ? optsOrMsg.message : (optsOrMsg instanceof Error ? optsOrMsg.message : optsOrMsg)
  const safeMsg = Array.isArray(rawMsg)
    ? rawMsg.map(x => (typeof x === 'string' ? x : (x?.msg || JSON.stringify(x)))).join('; ')
    : (typeof rawMsg === 'object' && rawMsg !== null ? (rawMsg.msg || rawMsg.message || JSON.stringify(rawMsg)) : String(rawMsg || ''))
  const entry = {
    id,
    type: tType,
    title: isObj ? (optsOrMsg.title || defaultTitle(tType)) : defaultTitle(tType),
    message: safeMsg,
    serverName: isObj ? (optsOrMsg.serverName || '') : '',
    durationSecs: isObj ? (optsOrMsg.durationSecs || 0) : 0,
    onClick: isObj && typeof optsOrMsg.onClick === 'function' ? optsOrMsg.onClick : null,
    duration: dur,
    remainingMs: dur,
    startedAt: Date.now(),
    paused: false,
  }
  toasts.value.push(entry)
  if (dur > 0) startTimer(id, dur)

  if (isObj && optsOrMsg.desktop && typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
    try {
      const body = (entry.serverName ? `[${entry.serverName}] ` : '') + entry.message + (entry.durationSecs ? ` (${entry.durationSecs}s)` : '')
      const n = new Notification(entry.title, { body, tag: `pantau-notif-${id}` })
      n.onclick = () => { window.focus(); if (entry.onClick) entry.onClick(); n.close() }
      setTimeout(() => { try { n.close() } catch (_) {} }, 5000)
    } catch (_) {}
  }
  return id
}

function dismissToast(id) {
  clearTimer(id)
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    dismiss: dismissToast,
    pause: pauseToast,
    resume: resumeToast,
    notify: (opts) => pushToast(opts),
    info: (msg, dur) => pushToast(msg, 'info', dur ?? 4500),
    success: (msg, dur) => pushToast(msg, 'success', dur ?? 4500),
    warning: (msg, dur) => pushToast(msg, 'warning', dur ?? 5000),
    error: (msg, dur) => pushToast(msg, 'error', dur ?? 5500),
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
