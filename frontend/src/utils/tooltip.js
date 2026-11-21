// Universal Selectable Tooltip Engine
export function initTooltipEngine() {
  if (typeof document === 'undefined') return

  let tipEl = document.getElementById('pantau-copy-tooltip')
  if (!tipEl) {
    tipEl = document.createElement('div')
    tipEl.id = 'pantau-copy-tooltip'
    tipEl.className = 'pantau-copy-tooltip'
    tipEl.setAttribute('role', 'tooltip')
    tipEl.setAttribute('aria-hidden', 'true')
    const tipText = document.createElement('div')
    tipText.id = 'pantau-tip-text'
    tipText.className = 'pantau-tip-text'
    tipEl.appendChild(tipText)
    document.body.appendChild(tipEl)
  }
  const tipTextEl = document.getElementById('pantau-tip-text')

  let currentTarget = null
  let showTimer = null
  let hideTimer = null
  let isHoveringTip = false

  function resolveTooltipTarget(el) {
    if (!el || el === document.body || el === document.documentElement) return null
    if (tipEl.contains(el)) return null

    let text = null
    if (el.hasAttribute('title')) {
      text = el.getAttribute('title').trim()
      if (text) {
        el.dataset.pantauTip = text
        el.removeAttribute('title')
      }
    } else if (el.dataset.pantauTip && el.dataset.pantauTip.trim()) {
      text = el.dataset.pantauTip.trim()
    } else if (el.hasAttribute('data-tooltip') && el.getAttribute('data-tooltip').trim()) {
      text = el.getAttribute('data-tooltip').trim()
    }

    if (text) {
      return { target: el, text }
    }
    return resolveTooltipTarget(el.parentElement)
  }

  function positionTooltip(target) {
    const rect = target.getBoundingClientRect()

    tipEl.style.visibility = 'hidden'
    tipEl.style.display = 'block'
    const tipRect = tipEl.getBoundingClientRect()

    const margin = 8
    let top = rect.top - tipRect.height - margin
    let left = rect.left + rect.width / 2 - tipRect.width / 2

    if (top < margin) {
      top = rect.bottom + margin
    }

    const maxLeft = window.innerWidth - tipRect.width - margin
    if (left < margin) left = margin
    if (left > maxLeft) left = maxLeft

    if (top + tipRect.height > window.innerHeight - margin) {
      top = Math.max(margin, window.innerHeight - tipRect.height - margin)
    }

    tipEl.style.top = Math.round(top) + 'px'
    tipEl.style.left = Math.round(left) + 'px'
    tipEl.style.visibility = 'visible'
  }

  function show(target, text) {
    clearTimeout(hideTimer)
    clearTimeout(showTimer)

    showTimer = setTimeout(() => {
      if (!target || !document.body.contains(target)) return
      currentTarget = target

      tipTextEl.textContent = text

      positionTooltip(target)
      tipEl.classList.add('show')
      tipEl.setAttribute('aria-hidden', 'false')
    }, 160)
  }

  function hide(delay = 180) {
    clearTimeout(showTimer)
    clearTimeout(hideTimer)

    hideTimer = setTimeout(() => {
      if (isHoveringTip) return
      tipEl.classList.remove('show')
      tipEl.setAttribute('aria-hidden', 'true')
      setTimeout(() => {
        if (!tipEl.classList.contains('show')) {
          tipEl.style.display = 'none'
          tipEl.style.visibility = 'hidden'
        }
      }, 120)
      currentTarget = null
    }, delay)
  }

  tipEl.addEventListener('mouseenter', () => {
    isHoveringTip = true
    clearTimeout(hideTimer)
  })

  tipEl.addEventListener('mouseleave', () => {
    isHoveringTip = false
    hide(150)
  })

  document.addEventListener('mouseover', (e) => {
    const res = resolveTooltipTarget(e.target)
    if (!res) return

    if (currentTarget !== res.target) {
      show(res.target, res.text)
    } else {
      clearTimeout(hideTimer)
    }
  }, { passive: true })

  document.addEventListener('mouseout', (e) => {
    if (!currentTarget) return
    const related = e.relatedTarget
    if (related && (currentTarget.contains(related) || tipEl.contains(related))) return
    hide(220)
  }, { passive: true })

  window.addEventListener('scroll', () => {
    if (!isHoveringTip) hide(0)
  }, { passive: true })

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hide(0)
  })

  document.addEventListener('click', (e) => {
    if (tipEl.contains(e.target)) return
    hide(0)
  })
}
