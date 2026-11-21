<template>
  <div
    v-show="isOpen && !isMinimized"
    class="fixed inset-0 z-[20000] flex items-center justify-center bg-black/60 backdrop-blur-xs p-2 sm:p-4 select-none"
    @click.self="handleBackdropClick"
  >
    <!-- TERMINAL DOCK WINDOW CONTAINER -->
    <div
      class="bg-[#0b0f19] border border-cyan-500/30 rounded-xl shadow-2xl flex flex-col overflow-hidden transition-all duration-150"
      :class="isMaximized ? 'fixed inset-0 w-screen h-screen rounded-none z-[30000] border-none' : 'w-[90vw] max-w-[1440px] h-[82vh] min-h-[500px]'"
    >
      <!-- 1. DOCK HEADER WITH TABS & CONTROLS -->
      <div class="bg-[#080d16] border-b border-cyan-500/20 px-3 pt-2 pb-0 flex items-end justify-between gap-3 select-none shrink-0 font-mono">
        <!-- TABS CONTAINER -->
        <div class="flex items-end gap-1.5 overflow-x-auto overflow-y-hidden flex-1 scrollbar-none pb-0">
          <!-- INDIVIDUAL TAB -->
          <div
            v-for="t in tabs"
            :key="t.id"
            @click="selectTab(t.id)"
            class="group relative inline-flex items-center gap-2 px-3 py-1.5 rounded-t-lg border-t border-x text-xs cursor-pointer transition-colors max-w-[220px]"
            :class="activeTabId === t.id
              ? 'bg-[#0b0f19] border-cyan-500/40 text-cyan-300 font-bold shadow-sm'
              : 'bg-[#0e1626]/60 border-gray-800 text-gray-400 hover:text-gray-200 hover:bg-[#121c30]'"
            :title="`${t.hostname} (${t.ip})`"
          >
            <!-- Status Dot (Connected / Disconnected) -->
            <span
              class="w-2 h-2 rounded-full shrink-0 transition"
              :class="t.status === 'connected' ? 'bg-emerald-400 beacon-live' : (t.status === 'connecting' ? 'bg-amber-400 animate-pulse' : 'bg-rose-500')"
            ></span>

            <!-- Hostname Label -->
            <span class="truncate">{{ t.hostname }}</span>

            <!-- Close Tab Button -->
            <button
              @click.stop="closeTab(t.id)"
              class="w-4 h-4 ml-1 flex items-center justify-center rounded text-gray-500 hover:text-rose-400 hover:bg-rose-950/40 transition shrink-0 cursor-pointer"
              title="Close Tab"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- NEW TAB BUTTON (+) -->
          <div class="relative shrink-0 pb-1">
            <button
              @click="toggleNewTabDropdown"
              class="px-2 py-1 rounded bg-[#0e1626] border border-cyan-900/60 hover:border-cyan-400/60 text-cyan-400 hover:text-white transition flex items-center gap-1 text-xs cursor-pointer font-bold"
              title="Open New Terminal Tab"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              <svg class="w-2.5 h-2.5 opacity-60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>

            <!-- DROPDOWN SEARCH LIST OF FLEET SERVERS -->
            <div
              v-if="showNewTabDropdown"
              class="absolute left-0 top-full mt-1.5 w-64 bg-[#0a0f1d] border border-cyan-500/40 rounded-lg shadow-2xl p-2 z-50 text-xs font-mono"
            >
              <input
                v-model="hostSearchQuery"
                type="text"
                placeholder="Search server..."
                class="w-full bg-[#050811] border border-cyan-900/60 focus:border-cyan-400 rounded px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 outline-none mb-1.5"
                autofocus
              />
              <div class="max-h-52 overflow-y-auto space-y-0.5 divide-y divide-gray-800/40">
                <div
                  v-for="s in filteredServers"
                  :key="s.id"
                  @click="openNewTabForServer(s)"
                  class="px-2 py-1.5 hover:bg-cyan-950/40 rounded cursor-pointer flex items-center justify-between transition"
                >
                  <span class="font-bold text-gray-200">{{ s.hostname }}</span>
                  <span class="text-[11px] text-gray-500 font-normal">{{ s.ip_address }}</span>
                </div>
                <div v-if="filteredServers.length === 0" class="p-2 text-center text-gray-500">
                  No matching servers
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- WINDOW CONTROLS (Icon-Only + Tooltip As Label Standard) -->
        <div class="flex items-center gap-1 pb-1">
          <!-- Clear Terminal -->
          <button
            @click="clearActiveTerminal"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40 transition cursor-pointer"
            title="Clear Screen"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
            </svg>
          </button>

          <!-- Minimize to Dock Shelf -->
          <button
            @click="$emit('minimize')"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40 transition cursor-pointer"
            title="Minimize to Dock"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>

          <!-- Maximize / Restore -->
          <button
            @click="isMaximized = !isMaximized"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40 transition cursor-pointer"
            :title="isMaximized ? 'Restore Window' : 'Maximize Window'"
          >
            <svg v-if="!isMaximized" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/>
            </svg>
            <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="14" height="14" x="7" y="7" rx="2"/>
              <path d="M17 3H5a2 2 0 0 0-2 2v12"/>
            </svg>
          </button>

          <!-- Pop-out Standalone Window -->
          <button
            @click="popoutTerminalWindow"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40 transition cursor-pointer"
            title="Pop-out Window"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </button>

          <!-- Close Dock -->
          <button
            @click="$emit('close')"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
            title="Close Dock"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 2. TERMINAL BODY WORKSPACES -->
      <div class="flex-1 bg-[#070b14] relative overflow-hidden flex flex-col">
        <!-- Render each tab's container (active displayed, inactive hidden) -->
        <div
          v-for="t in tabs"
          :key="t.id"
          v-show="activeTabId === t.id"
          :id="`term-container-${t.id}`"
          class="w-full h-full p-2 overflow-hidden flex-1"
        ></div>

        <!-- Empty state when no tabs are open -->
        <div
          v-if="tabs.length === 0"
          class="flex-1 flex flex-col items-center justify-center text-gray-500 font-mono text-xs gap-3"
        >
          <svg class="w-10 h-10 text-gray-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
          <span>No active terminal sessions. Open a tab to connect.</span>
          <button
            @click="toggleNewTabDropdown"
            class="px-3 py-1.5 rounded bg-cyan-950/80 border border-cyan-600/60 text-cyan-300 hover:bg-cyan-800 hover:text-white transition cursor-pointer font-bold flex items-center gap-1.5"
          >
            <span>+ Connect New Server</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  isMinimized: { type: Boolean, default: false },
  fleetServers: { type: Array, default: () => [] },
  initialServer: { type: Object, default: null }
})

const emit = defineEmits(['close', 'minimize', 'restore'])

const isMaximized = ref(false)
const showNewTabDropdown = ref(false)
const hostSearchQuery = ref('')
const activeTabId = ref(null)
const tabs = ref([])

const filteredServers = computed(() => {
  if (!hostSearchQuery.value) return props.fleetServers
  const q = hostSearchQuery.value.toLowerCase()
  return props.fleetServers.filter(
    (s) => s.hostname.toLowerCase().includes(q) || (s.ip_address || '').includes(q)
  )
})

function toggleNewTabDropdown() {
  showNewTabDropdown.value = !showNewTabDropdown.value
  if (showNewTabDropdown.value) {
    hostSearchQuery.value = ''
  }
}

function handleBackdropClick() {
  emit('minimize')
}

function selectTab(id) {
  activeTabId.value = id
  showNewTabDropdown.value = false
  nextTick(() => {
    const active = tabs.value.find(t => t.id === id)
    if (active && active.fit) {
      try {
        active.fit.fit()
        active.term.focus()
      } catch (e) {}
    }
  })
}

function clearActiveTerminal() {
  const active = tabs.value.find(t => t.id === activeTabId.value)
  if (active && active.term) {
    active.term.clear()
  }
}

function popoutTerminalWindow() {
  const active = tabs.value.find(t => t.id === activeTabId.value)
  const sid = active ? active.serverId : (props.initialServer?.id || '')
  window.open(
    `/?standalone=terminal&sid=${sid}`,
    `pantau_term_dock`,
    'popup=yes,width=1200,height=800,menubar=no,toolbar=no,status=no'
  )
}

function openNewTabForServer(server) {
  showNewTabDropdown.value = false
  const targetDir = server.workingDirectory || ''
  const existing = tabs.value.find(t => t.serverId === server.id)
  if (existing) {
    selectTab(existing.id)
    if (targetDir) {
      sendCdToTab(existing, targetDir)
    }
    return
  }

  const tabId = 'tab_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5)
  const newTab = {
    id: tabId,
    serverId: server.id,
    hostname: server.hostname,
    ip: server.ip_address || '127.0.0.1',
    workingDirectory: targetDir,
    status: 'connecting',
    term: null,
    fit: null,
    ws: null
  }
  tabs.value.push(newTab)
  activeTabId.value = tabId

  nextTick(() => {
    initTerminalForTab(newTab)
  })
}

function sendCdToTab(tab, path) {
  if (!path) return
  tab.workingDirectory = path
  const cleanPath = path.replace(/'/g, "'\\''")
  const cmd = `cd '${cleanPath}'\n`
  if (tab.ws && tab.ws.readyState === WebSocket.OPEN) {
    tab.ws.send(JSON.stringify({ type: 'input', data: cmd }))
    if (tab.term) {
      setTimeout(() => {
        try { tab.term.focus() } catch (e) {}
      }, 50)
    }
  }
}

function initTerminalForTab(tab) {
  const container = document.getElementById(`term-container-${tab.id}`)
  if (!container) return

  const term = new Terminal({
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
      white: '#f8fafc',
    }
  })

  const fit = new FitAddon()
  term.loadAddon(fit)
  term.open(container)
  tab.term = term
  tab.fit = fit

  try {
    fit.fit()
  } catch (e) {}

  // Hubungkan ke WebSocket Backend
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const token = localStorage.getItem('pantau_token') || ''
  let wsUrl = `${protocol}//${window.location.host}/ws/servers/${tab.serverId}/terminal?token=${encodeURIComponent(token)}`
  if (tab.workingDirectory) {
    wsUrl += `&cwd=${encodeURIComponent(tab.workingDirectory)}`
  }

  const ws = new WebSocket(wsUrl)
  tab.ws = ws

  ws.onopen = () => {
    tab.status = 'connected'
    fit.fit()
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    term.focus()

    if (tab.workingDirectory) {
      const cleanPath = tab.workingDirectory.replace(/'/g, "'\\''")
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'input', data: `cd '${cleanPath}'\n` }))
        }
      }, 400)
    }
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'stdout' && msg.data) {
        term.write(msg.data)
      }
    } catch (e) {
      term.write(event.data)
    }
  }

  ws.onclose = () => {
    tab.status = 'disconnected'
    term.write('\r\n\x1b[31;1m[DISCONNECTED] Terminal session terminated.\x1b[0m\r\n')
  }

  ws.onerror = () => {
    tab.status = 'disconnected'
  }

  term.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }))
    }
  })

  term.onResize((size) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }))
    }
  })

  window.addEventListener('resize', () => {
    if (activeTabId.value === tab.id) {
      try { fit.fit() } catch (e) {}
    }
  })
}

function closeTab(tabId) {
  const idx = tabs.value.findIndex(t => t.id === tabId)
  if (idx === -1) return

  const closing = tabs.value[idx]
  if (closing.ws) {
    try { closing.ws.close() } catch (e) {}
  }
  if (closing.term) {
    try { closing.term.dispose() } catch (e) {}
  }

  tabs.value.splice(idx, 1)

  if (activeTabId.value === tabId) {
    if (tabs.value.length > 0) {
      const nextIdx = Math.max(0, idx - 1)
      selectTab(tabs.value[nextIdx].id)
    } else {
      activeTabId.value = null
      emit('close')
    }
  }
}

// Watch initialServer to open tab automatically when opened with a server
watch(() => props.initialServer, (newServer) => {
  if (newServer && props.isOpen) {
    openNewTabForServer(newServer)
  }
}, { immediate: true })

watch(() => props.isOpen, (open) => {
  if (open) {
    if (props.initialServer && tabs.value.length === 0) {
      openNewTabForServer(props.initialServer)
    } else if (tabs.value.length > 0 && activeTabId.value) {
      nextTick(() => {
        const active = tabs.value.find(t => t.id === activeTabId.value)
        if (active && active.fit) {
          try {
            active.fit.fit()
            active.term.focus()
          } catch (e) {}
        }
      })
    }
  }
})

watch(isMaximized, () => {
  nextTick(() => {
    const active = tabs.value.find(t => t.id === activeTabId.value)
    if (active && active.fit) {
      try { active.fit.fit() } catch (e) {}
    }
  })
})

onUnmounted(() => {
  for (const t of tabs.value) {
    if (t.ws) try { t.ws.close() } catch (e) {}
    if (t.term) try { t.term.dispose() } catch (e) {}
  }
})

defineExpose({
  openNewTabForServer,
  selectTab,
  tabs
})
</script>

<style scoped>
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  scrollbar-width: none;
  -ms-overflow-style: none;
}
</style>
