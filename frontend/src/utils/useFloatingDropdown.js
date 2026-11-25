import { ref, onMounted, onUnmounted } from 'vue'

export function useFloatingDropdown(menuHeight = 160, widthPx = 176) {
  const openId = ref(null)
  const activeItem = ref(null)
  const dropdownStyle = ref({})

  function close() {
    openId.value = null
    activeItem.value = null
  }

  function toggle(item, event) {
    if (!item) return
    if (openId.value === item.id) {
      close()
      return
    }
    openId.value = item.id
    activeItem.value = item
    if (event?.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect()
      const vh = window.innerHeight
      const vw = window.innerWidth
      const spaceBelow = vh - rect.bottom
      const isDropup = spaceBelow < menuHeight + 10 && rect.top > spaceBelow
      const rightOffset = Math.max(8, vw - rect.right)
      dropdownStyle.value = isDropup
        ? { position: 'fixed', bottom: `${Math.max(8, vh - rect.top + 4)}px`, right: `${rightOffset}px`, width: `${widthPx}px` }
        : { position: 'fixed', top: `${Math.max(8, rect.bottom + 4)}px`, right: `${rightOffset}px`, width: `${widthPx}px` }
    }
  }

  onMounted(() => {
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
  })

  onUnmounted(() => {
    window.removeEventListener('click', close)
    window.removeEventListener('scroll', close, true)
    window.removeEventListener('resize', close)
  })

  return { openId, activeItem, dropdownStyle, toggle, close }
}
