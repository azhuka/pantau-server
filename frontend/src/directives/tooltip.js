import { showTooltip, hideTooltip } from '../composables/useTooltip'

export const tooltipDirective = {
  mounted(el, binding) {
    // If element has a native title attribute, capture it and remove to suppress OS browser tooltip
    if (el.hasAttribute('title') && !binding.value) {
      el._nativeTitle = el.getAttribute('title')
      el.removeAttribute('title')
    }

    el._onMouseEnter = () => {
      let val = binding.value || el._nativeTitle || el.getAttribute('data-tooltip')
      if (typeof val === 'function') {
        val = val()
      }
      if (val) {
        showTooltip(val, el)
      }
    }

    el._onMouseLeave = () => {
      hideTooltip(false)
    }

    el.addEventListener('mouseenter', el._onMouseEnter)
    el.addEventListener('mouseleave', el._onMouseLeave)
  },

  updated(el, binding) {
    if (el.hasAttribute('title') && !binding.value) {
      el._nativeTitle = el.getAttribute('title')
      el.removeAttribute('title')
    }
  },

  unmounted(el) {
    if (el._onMouseEnter) el.removeEventListener('mouseenter', el._onMouseEnter)
    if (el._onMouseLeave) el.removeEventListener('mouseleave', el._onMouseLeave)
  },
}
