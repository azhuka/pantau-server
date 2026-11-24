<template>
  <div
    class="terminal-window transition-all duration-200"
    :class="isFullscreen ? 'is-fullscreen' : 'w-full my-3'"
  >
    <!-- 1. TERMINAL TITLEBAR -->
    <div class="terminal-titlebar">
      <!-- Title & Hostname -->
      <div class="terminal-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="inline-block shrink-0 mr-1.5">
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
        <span>{{ t('term_title_default') }} &middot; {{ server?.hostname }}</span>
      </div>

      <!-- Action Badges & Buttons -->
      <div class="terminal-actions">
        <!-- Active Session Beacon Banner -->
        <span
          v-if="isConnected"
          id="term-active-banner"
          class="terminal-status-badge font-semibold"
          style="color:#86efac; background:rgba(34,197,94,0.15); border:1px solid rgba(34,197,94,0.35); font-size:11px; padding:2px 8px; border-radius:4px"
          :title="t('term_session_active_badge')"
        >
          <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:#22c55e; margin-right:5px; box-shadow:0 0 6px #22c55e"></span>
          <span>{{ t('term_session_active_badge') }}</span>
        </span>

        <!-- Lease Countdown Timer Badge -->
        <span
          v-if="leaseSeconds > 0"
          id="term-lease-badge"
          class="terminal-status-badge"
          style="color:#facc15; border:1px solid rgba(234,179,8,0.3); background:rgba(234,179,8,0.08); padding:1px 6px; border-radius:4px; font-family:monospace; font-size:11px"
          :title="t('term_lease_tooltip')"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle; margin-right:3px">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span>{{ formatLeaseTime(leaseSeconds) }}</span>
        </span>

        <!-- Lock Button (Red) -->
        <button
          type="button"
          @click="$emit('request-lock')"
          class="terminal-btn-icon"
          style="color:#ff7b72"
          :title="t('term_lock_tooltip')"
          aria-label="Lock"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </button>

        <!-- Status Dot & Text -->
        <span class="terminal-status-badge" :style="{ color: isConnected ? '#3fb950' : '#8b949e' }">
          <span class="t-status-dot" :class="isConnected ? 'active' : 'closed'"></span>
          <span class="hidden sm:inline">{{ isConnected ? t('term_status_active') : t('term_status_closed') }}</span>
        </span>

        <!-- Clear Screen Button -->
        <button
          type="button"
          @click="clearScreen"
          class="terminal-btn-icon"
          :title="t('term_clear_tooltip')"
          aria-label="Clear Screen"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
        </button>

        <!-- Fullscreen Toggle Button -->
        <button
          type="button"
          @click="toggleFullscreen"
          class="terminal-btn-icon"
          :class="{ 'is-active': isFullscreen }"
          :title="isFullscreen ? t('term_exit_fullscreen_tooltip') : t('term_fullscreen_tooltip')"
          aria-label="Fullscreen"
        >
          <svg v-if="!isFullscreen" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </svg>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3" />
          </svg>
        </button>

        <!-- Close Button -->
        <button
          type="button"
          @click="$emit('request-close')"
          class="terminal-btn-icon"
          :title="t('term_close_tooltip')"
          aria-label="Close"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 2. TERMINAL SCREEN CANVAS -->
    <div
      ref="screenRef"
      class="real-terminal-screen"
      tabindex="0"
      :aria-label="t('term_title_default')"
      :style="isFullscreen ? {} : { height: `${terminalHeight}px`, maxHeight: '65vh' }"
    >
      <div ref="terminalContainerRef" class="w-full h-full"></div>
    </div>

    <!-- 3. RESIZE GRIP HANDLE -->
    <div
      v-if="!isFullscreen"
      @mousedown="startResize"
      class="terminal-resize-handle"
      :class="{ 'is-resizing': isResizing }"
      :title="t('term_resize_handle_tooltip')"
    >
      <span class="resize-grip"></span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { useI18n } from '../../i18n'

const props = defineProps({
  server: { type: Object, required: true },
  leaseSeconds: { type: Number, default: 0 }
})

const emit = defineEmits(['request-close', 'request-lock'])
const { t } = useI18n()

const screenRef = ref(null)
const terminalContainerRef = ref(null)
const isFullscreen = ref(false)
const isConnected = ref(false)
const isResizing = ref(false)
const terminalHeight = ref(480)

let term = null
let fitAddon = null
let ws = null
let resizeObserver = null

function formatLeaseTime(secs) {
  if (secs < 0) secs = 0
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0')
}

function clearScreen() {
  if (term) {
    term.clear()
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data: '\x15\x0c' }))
    }
    term.focus()
  }
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  nextTick(() => {
    setTimeout(() => {
      if (fitAddon) fitAddon.fit()
      if (term) term.focus()
    }, 50)
  })
}

function startResize(e) {
  isResizing.value = true
  const startY = e.clientY
  const startH = terminalHeight.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'ns-resize'

  function onMouseMove(moveEvent) {
    const delta = moveEvent.clientY - startY
    terminalHeight.value = Math.max(220, Math.min(window.innerHeight * 0.9, startH + delta))
    if (fitAddon) fitAddon.fit()
  }

  function onMouseUp() {
    isResizing.value = false
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
    if (fitAddon) fitAddon.fit()
    if (term) term.focus()
  }

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function initTerminal() {
  if (!terminalContainerRef.value || term) return

  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    fontSize: 13,
    lineHeight: 1.25,
    theme: {
      background: '#0d1117',
      foreground: '#c9d1d9',
      cursor: '#58a6ff',
      selectionBackground: 'rgba(56, 139, 253, 0.4)',
      black: '#484f58',
      red: '#ff7b72',
      green: '#3fb950',
      yellow: '#d29922',
      blue: '#58a6ff',
      magenta: '#bc8cff',
      cyan: '#39c5cf',
      white: '#b1bac4',
      brightBlack: '#6e7681',
      brightRed: '#ffa198',
      brightGreen: '#56d364',
      brightYellow: '#e3b341',
      brightBlue: '#79c0ff',
      brightMagenta: '#d2a8ff',
      brightCyan: '#56d4dd',
      brightWhite: '#f0f6fc'
    },
    convertEol: true,
    scrollback: 5000
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(terminalContainerRef.value)

  try {
    fitAddon.fit()
  } catch (e) {}

  term.onData(data => {
    if (!data) return
    const filtered = (typeof data === 'string')
      ? data.replace(/\x1b\[[?>!][0-9;]*c/g, '').replace(/\x1b\[\??[0-9]+;[0-9]+R/g, '').replace(/\x1b\[[0-9]+n/g, '').replace(/\x1b\](?:10|11);[^\x07\x1b]*(?:\x07|\x1b\\)/g, '')
      : data
    if (filtered && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data: filtered }))
    }
  })

  term.onResize(size => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }))
    }
  })

  term.attachCustomKeyEventHandler(e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) {
      if (term.hasSelection()) {
        if (e.type === 'keydown' && navigator.clipboard) {
          navigator.clipboard.writeText(term.getSelection()).catch(() => {})
        }
        return false
      }
      return true
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'v' || e.key === 'V')) {
      if (e.type === 'keydown' && navigator.clipboard) {
        navigator.clipboard.readText().then(text => {
          if (text && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'input', data: text }))
          }
        }).catch(() => {})
      }
      return false
    }
    if (e.key === 'Escape' && isFullscreen.value) {
      if (e.type === 'keydown') toggleFullscreen()
      return false
    }
    return true
  })

  // Right-click contextmenu: copy if selected, else paste
  if (screenRef.value) {
    screenRef.value.addEventListener('contextmenu', (e) => {
      e.preventDefault()
      if (term && term.hasSelection()) {
        const sel = term.getSelection()
        if (navigator.clipboard) navigator.clipboard.writeText(sel).catch(() => {})
        term.clearSelection()
      } else if (navigator.clipboard) {
        navigator.clipboard.readText().then(text => {
          if (text && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'input', data: text }))
          }
        }).catch(() => {})
      }
      if (term) term.focus()
    })

    screenRef.value.addEventListener('click', () => {
      if (term) term.focus()
    })
  }

  connectWs()

  if (window.ResizeObserver && screenRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (fitAddon) {
        try { fitAddon.fit() } catch (e) {}
      }
    })
    resizeObserver.observe(screenRef.value)
  }
}

function connectWs() {
  if (ws) {
    try { ws.close() } catch (e) {}
    ws = null
  }

  const proto = (window.location.protocol === 'https:') ? 'wss:' : 'ws:'
  const token = localStorage.getItem('pantau_token') || ''
  const wsUrl = `${proto}//${window.location.host}/ws/servers/${props.server.id}/terminal?token=${encodeURIComponent(token)}`

  term.write(`\x1b[90m[${t('term_connecting')}]\x1b[0m\r\n`)

  try {
    ws = new WebSocket(wsUrl)
  } catch (err) {
    term.write(`\r\n\x1b[31m[WebSocket connection error: ${err.message}]\x1b[0m\r\n`)
    return
  }

  ws.onopen = () => {
    isConnected.value = true
    if (fitAddon) fitAddon.fit()
    if (term) {
      ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      term.focus()
    }
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'stdout' && msg.data) {
        const sanitized = (typeof msg.data === 'string')
          ? msg.data.replace(/\x1b\[c|\x1b\[0c|\x1b\[>c|\x1b\[>0c|\x1b\[>q/g, '')
          : msg.data
        if (sanitized && term) term.write(sanitized)
      }
    } catch (e) {
      if (term) term.write(event.data)
    }
  }

  ws.onclose = () => {
    isConnected.value = false
    if (term) {
      term.write(`\r\n\x1b[90m[${t('term_session_closed')}]\x1b[0m\r\n`)
    }
  }
}

onMounted(() => {
  nextTick(() => {
    initTerminal()
  })
})

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect()
  if (ws) {
    try { ws.close() } catch (e) {}
    ws = null
  }
  if (term) {
    try { term.dispose() } catch (e) {}
    term = null
  }
})
</script>

<style scoped>
.terminal-window {
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  border: 1px solid #30363d;
  background: #0d1117;
  transition: all 0.2s ease;
}

.terminal-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 14px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  user-select: none;
}

.terminal-title {
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  color: #c9d1d9;
  display: flex;
  align-items: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.terminal-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.terminal-btn-icon {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  font-size: 11px;
  padding: 4px 9px;
  border-radius: 5px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
  white-space: nowrap;
  font-family: inherit;
}

.terminal-btn-icon:hover {
  background: #30363d;
  color: #fff;
  border-color: #484f58;
}

.terminal-btn-icon.is-active {
  background: rgba(56, 189, 248, 0.16);
  border-color: rgba(56, 189, 248, 0.45);
  color: #38bdf8;
}

.terminal-status-badge {
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

.t-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.t-status-dot.active {
  background: #27c93f;
  box-shadow: 0 0 6px rgba(39, 201, 63, 0.6);
}

.t-status-dot.closed {
  background: #ff5f56;
}

.real-terminal-screen {
  padding: 10px 14px !important;
  background: #0d1117 !important;
  height: 480px;
  box-sizing: border-box;
  overflow: hidden !important;
  position: relative;
}

.real-terminal-screen :deep(.xterm) {
  height: 100%;
}

.real-terminal-screen :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

.real-terminal-screen :deep(.xterm-viewport::-webkit-scrollbar) {
  width: 8px;
}

.real-terminal-screen :deep(.xterm-viewport::-webkit-scrollbar-track) {
  background: #0d1117;
}

.real-terminal-screen :deep(.xterm-viewport::-webkit-scrollbar-thumb) {
  background: #30363d;
  border-radius: 4px;
}

.real-terminal-screen :deep(.xterm-viewport::-webkit-scrollbar-thumb:hover) {
  background: #484f58;
}

.terminal-resize-handle {
  height: 10px;
  background: #161b22;
  border-top: 1px solid #30363d;
  border-radius: 0 0 8px 8px;
  cursor: ns-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.terminal-resize-handle:hover,
.terminal-resize-handle.is-resizing {
  background: #21262d;
  border-color: #58a6ff;
}

.resize-grip {
  width: 36px;
  height: 3px;
  border-radius: 2px;
  background: #484f58;
}

.terminal-resize-handle:hover .resize-grip,
.terminal-resize-handle.is-resizing .resize-grip {
  background: #58a6ff;
}

.terminal-window.is-fullscreen {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  max-width: 100vw !important;
  max-height: 100vh !important;
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
  z-index: 35000 !important;
  display: flex !important;
  flex-direction: column !important;
  box-shadow: none !important;
  background: #0d1117 !important;
}

.terminal-window.is-fullscreen .terminal-titlebar {
  flex: 0 0 44px !important;
  height: 44px !important;
  padding: 0 16px !important;
  background: #161b22 !important;
  border-bottom: 1px solid #30363d !important;
  border-radius: 0 !important;
  box-sizing: border-box !important;
}

.terminal-window.is-fullscreen .real-terminal-screen {
  flex: 1 1 auto !important;
  width: 100% !important;
  height: calc(100vh - 44px) !important;
  max-height: calc(100vh - 44px) !important;
  border-radius: 0 !important;
  padding: 12px 16px !important;
  box-sizing: border-box !important;
  background: #0d1117 !important;
  overflow: hidden !important;
}
</style>
