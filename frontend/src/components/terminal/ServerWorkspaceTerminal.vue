<template>
  <div
    class="w-full bg-[#0a0e17] border border-cyan-500/30 rounded-lg shadow-xl overflow-hidden flex flex-col font-mono text-xs select-none my-2 transition-all duration-150"
    :class="isFullscreen ? 'fixed inset-4 z-[35000] my-0 rounded-xl shadow-[0_25px_70px_rgba(0,0,0,0.95)] border-cyan-400' : ''"
  >
    <!-- TERMINAL TITLEBAR -->
    <div class="bg-[#070b14] border-b border-cyan-500/20 px-3 py-1.5 flex items-center justify-between gap-3 shrink-0">
      <!-- Left: Title & Host Info -->
      <div class="flex items-center gap-2 text-cyan-300 font-bold min-w-0">
        <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="4 17 10 11 4 5"/>
          <line x1="12" y1="19" x2="20" y2="19"/>
        </svg>
        <span class="truncate">{{ t('term_title_default') }} &middot; {{ server?.hostname }}</span>
      </div>

      <!-- Right: Badges & Controls -->
      <div class="flex items-center gap-2 shrink-0">
        <!-- Active Session Beacon Badge -->
        <span
          v-if="isConnected"
          class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-600/50"
          :title="t('term_session_active_badge')"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
          <span>{{ t('term_session_active_badge') }}</span>
        </span>

        <!-- Lease Countdown Timer Badge -->
        <span
          v-if="leaseSeconds > 0"
          class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-amber-950/70 text-amber-300 border border-amber-600/50"
          :title="t('term_lease_tooltip')"
        >
          <svg class="w-3 h-3 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          <span>{{ formatLeaseTime(leaseSeconds) }}</span>
        </span>

        <!-- Lock Button -->
        <button
          type="button"
          @click="$emit('request-lock')"
          class="p-1 rounded text-rose-400 hover:text-white hover:bg-rose-950/60 transition cursor-pointer"
          :title="t('term_lock_tooltip')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </button>

        <!-- Clear Screen Button -->
        <button
          type="button"
          @click="clearScreen"
          class="p-1 rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition cursor-pointer"
          :title="t('term_clear_tooltip')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
        </button>

        <!-- Fullscreen Button -->
        <button
          type="button"
          @click="toggleFullscreen"
          class="p-1 rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/60 transition cursor-pointer"
          :title="isFullscreen ? t('term_exit_fullscreen_tooltip') : t('term_fullscreen_tooltip')"
        >
          <svg v-if="!isFullscreen" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
          </svg>
          <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
          </svg>
        </button>

        <!-- Close Button -->
        <button
          type="button"
          @click="$emit('request-close')"
          class="p-1 rounded text-gray-400 hover:text-white hover:bg-white/10 transition cursor-pointer"
          :title="t('term_close_tooltip')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- TERMINAL CANVAS -->
    <div
      ref="terminalContainerRef"
      class="w-full bg-[#070b14] p-1 overflow-hidden"
      :style="{ height: isFullscreen ? 'calc(100% - 40px)' : `${terminalHeight}px` }"
    ></div>

    <!-- RESIZE HANDLE (Drag height) -->
    <div
      v-if="!isFullscreen"
      @mousedown="startResize"
      class="h-2 w-full bg-[#060910] hover:bg-cyan-500/30 cursor-ns-resize flex items-center justify-center transition border-t border-cyan-950/60"
      :title="t('term_resize_handle_tooltip')"
    >
      <span class="w-8 h-1 rounded-full bg-cyan-700/50"></span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
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

const terminalContainerRef = ref(null)
const isFullscreen = ref(false)
const isConnected = ref(false)
const terminalHeight = ref(320)

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
  const startY = e.clientY
  const startH = terminalHeight.value

  function onMouseMove(moveEvent) {
    const delta = moveEvent.clientY - startY
    terminalHeight.value = Math.max(200, Math.min(750, startH + delta))
    if (fitAddon) fitAddon.fit()
  }

  function onMouseUp() {
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
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    fontSize: 13,
    lineHeight: 1.25,
    theme: {
      background: '#070b14',
      foreground: '#e2e8f0',
      cursor: '#38bdf8',
      selectionBackground: '#1e293b',
      black: '#0f172a',
      red: '#f43f5e',
      green: '#10b981',
      yellow: '#f59e0b',
      blue: '#38bdf8',
      magenta: '#c084fc',
      cyan: '#06b6d4',
      white: '#f8fafc'
    }
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(terminalContainerRef.value)

  try {
    fitAddon.fit()
  } catch (e) {}

  // Key handler & copy/paste
  term.onData(data => {
    if (!data) return
    const filtered = (typeof data === 'string')
      ? data.replace(/\x1b\[[?>!][0-9;]*c/g, '').replace(/\x1b\[\??[0-9]+;[0-9]+R/g, '').replace(/\x1b\[[0-9]+n/g, '')
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

  connectWs()

  if (window.ResizeObserver && terminalContainerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (fitAddon) {
        try { fitAddon.fit() } catch (e) {}
      }
    })
    resizeObserver.observe(terminalContainerRef.value)
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
