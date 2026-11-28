import { onMounted, onUnmounted } from 'vue'

const stack = []
let listenerAttached = false

function onKeyDown(e) {
  if (e.key !== 'Escape') return
  for (let i = stack.length - 1; i >= 0; i--) {
    const item = stack[i]
    if (item.isOpen()) {
      e.preventDefault()
      e.stopImmediatePropagation()
      item.close()
      return
    }
  }
}

/**
 * Register a modal on the global Escape stack (capture phase, topmost-first).
 * @param {Function} isOpen - Returns true when the modal is currently visible.
 * @param {Function} onClose - Callback invoked when Escape is pressed.
 */
export function useModalEsc(isOpen, onClose) {
  const entry = {
    isOpen: typeof isOpen === 'function' ? isOpen : () => true,
    close: onClose,
  }
  onMounted(() => {
    stack.push(entry)
    if (!listenerAttached && typeof window !== 'undefined') {
      window.addEventListener('keydown', onKeyDown, true)
      listenerAttached = true
    }
  })
  onUnmounted(() => {
    const idx = stack.indexOf(entry)
    if (idx !== -1) stack.splice(idx, 1)
  })
}
