import { reactive } from 'vue'

export const tooltipState = reactive({
  visible: false,
  title: '',
  text: '',
  extra: '',
  code: false,
  copyable: true,
  copied: false,
  x: 0,
  y: 0,
})

let showTimer = null
let hideTimer = null
let copiedTimer = null

export function positionTooltip(targetEl, options = {}) {
  if (!targetEl || typeof targetEl.getBoundingClientRect !== 'function') return

  const rect = targetEl.getBoundingClientRect()
  const textLen = (options.text || '').length
  const preferredWidth = Math.min(340, Math.max(120, textLen * 7.5 + 40))
  const estimatedHeight = textLen > 60 ? 50 : 32

  // Center horizontally relative to target element
  let left = rect.left + rect.width / 2 - preferredWidth / 2
  // Position above the target by default with 6px gap
  let top = rect.top - estimatedHeight - 6

  // Collision handling:
  // If too close to the top of the viewport, position below target
  if (top < 8) {
    top = rect.bottom + 6
  }

  // Ensure horizontal bounds stay safely within viewport
  const maxLeft = Math.max(8, window.innerWidth - preferredWidth - 12)
  left = Math.max(8, Math.min(left, maxLeft))

  // Ensure vertical bounds do not overflow bottom
  if (top + estimatedHeight > window.innerHeight - 8) {
    top = Math.max(8, window.innerHeight - estimatedHeight - 12)
  }

  tooltipState.x = Math.round(left)
  tooltipState.y = Math.round(top)
}

export function showTooltip(payload, targetEl) {
  if (!payload) return

  const text = typeof payload === 'string' ? payload : (payload.text || '')
  if (!text) return

  clearTimeout(hideTimer)

  const title = typeof payload === 'object' && payload.title ? payload.title : ''
  const extra = typeof payload === 'object' && payload.extra ? payload.extra : ''
  const code = typeof payload === 'object' && payload.code === true
  const copyable = typeof payload === 'object' && payload.copyable !== undefined ? payload.copyable : true

  clearTimeout(showTimer)
  showTimer = setTimeout(() => {
    tooltipState.title = title
    tooltipState.text = text
    tooltipState.extra = extra
    tooltipState.code = code
    tooltipState.copyable = copyable
    tooltipState.copied = false
    positionTooltip(targetEl, { text, code })
    tooltipState.visible = true
  }, 100)
}

export function hideTooltip(immediate = false) {
  clearTimeout(showTimer)
  clearTimeout(hideTimer)

  if (immediate) {
    tooltipState.visible = false
    tooltipState.copied = false
  } else {
    hideTimer = setTimeout(() => {
      tooltipState.visible = false
      tooltipState.copied = false
    }, 250)
  }
}

export function cancelHide() {
  clearTimeout(hideTimer)
}

export async function copyContent(customText = null) {
  const textToCopy = customText || tooltipState.text
  if (!textToCopy) return

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(textToCopy)
    } else {
      const ta = document.createElement('textarea')
      ta.value = textToCopy
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      ta.style.top = '-9999px'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.focus()
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }

    tooltipState.copied = true
    clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => {
      tooltipState.copied = false
    }, 1800)
  } catch (err) {
    console.warn('Failed to copy text:', err)
  }
}

export function useTooltip() {
  return {
    tooltipState,
    showTooltip,
    hideTooltip,
    cancelHide,
    copyContent,
  }
}
