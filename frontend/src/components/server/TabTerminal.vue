<template>
  <div class="space-y-3">
    <!-- Terminal Header Bar -->
    <div class="flex items-center justify-between bg-noc-card border border-noc-border p-2.5 rounded-lg text-xs">
      <div class="flex items-center gap-2">
        <span class="font-bold text-noc-text uppercase tracking-wider flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full" :class="connected ? 'bg-emerald-400' : 'bg-rose-500'"></span>
          Sesi Terminal PTY Langsung
        </span>
        <span v-if="connected" class="noc-badge noc-badge-green text-[10px]">Tersambung (WebSocket)</span>
        <span v-else class="noc-badge noc-badge-gray text-[10px]">Terputus</span>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="!unlocked"
          @click="showUnlockModal = true"
          class="noc-btn noc-btn-primary py-1 px-2.5"
        >
          Buka Kunci Terminal 🔒
        </button>
        <template v-else>
          <button
            @click="reconnect"
            class="noc-btn noc-btn-secondary py-1 px-2.5"
          >
            Hubungkan Ulang
          </button>
          <button
            @click="lockTerminal"
            class="noc-btn noc-btn-secondary py-1 px-2 text-rose-400"
            title="Kunci sesi terminal"
          >
            Kunci Sesi
          </button>
        </template>
      </div>
    </div>

    <!-- Terminal Container -->
    <div class="noc-card p-2 bg-[#090d16] border-noc-border">
      <div v-if="!unlocked" class="py-16 text-center text-noc-muted text-xs space-y-3">
        <div class="text-3xl">🔒</div>
        <div class="font-bold text-noc-text">Terminal Terproteksi Kebijakan Keamanan</div>
        <p class="max-w-md mx-auto text-[11px]">
          Sesi root terminal web dilindungi oleh otentikasi kata sandi operator untuk mencegah akses tidak sah.
        </p>
        <button @click="showUnlockModal = true" class="noc-btn noc-btn-primary py-1.5 px-4 text-xs font-semibold">
          Masukkan Kredensial untuk Membuka Sesi
        </button>
      </div>

      <div v-show="unlocked" ref="terminalContainer" class="w-full h-[520px] rounded overflow-hidden"></div>
    </div>

    <!-- Unlock Modal -->
    <div v-if="showUnlockModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
      <div class="w-full max-w-sm noc-card p-5 border-noc-border shadow-2xl relative">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border mb-4">
          <h2 class="text-sm font-bold uppercase tracking-tight text-noc-text">Buka Akses Terminal PTY</h2>
          <button @click="showUnlockModal = false" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <form @submit.prevent="handleUnlock" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Kata Sandi Operator</label>
            <input
              v-model="unlockPassword"
              type="password"
              required
              placeholder="••••••••••••"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div v-if="unlockError" class="p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
            {{ unlockError }}
          </div>

          <div class="pt-3 border-t border-noc-border flex justify-end gap-2">
            <button type="button" @click="showUnlockModal = false" class="noc-btn noc-btn-secondary">
              Batal
            </button>
            <button type="submit" :disabled="unlocking" class="noc-btn noc-btn-primary">
              {{ unlocking ? 'Memverifikasi...' : 'Buka Kunci' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
})

const terminalContainer = ref(null)
const unlocked = ref(false)
const connected = ref(false)
const showUnlockModal = ref(false)
const unlockPassword = ref('')
const unlocking = ref(false)
const unlockError = ref('')

let term = null
let fitAddon = null
let ws = null

async function checkStatus() {
  try {
    const res = await api.get(`/api/servers/${props.serverId}/terminal/status`)
    unlocked.value = res?.unlocked || false
    if (unlocked.value) {
      await nextTick()
      initTerminal()
    }
  } catch (e) {
    unlocked.value = false
  }
}

async function handleUnlock() {
  unlocking.value = true
  unlockError.value = ''
  try {
    const formData = new FormData()
    formData.append('password', unlockPassword.value)
    await api.post(`/api/servers/${props.serverId}/terminal/unlock`, formData)
    unlocked.value = true
    showUnlockModal.value = false
    unlockPassword.value = ''
    await nextTick()
    initTerminal()
  } catch (err) {
    unlockError.value = err.message || 'Kata sandi tidak valid'
  } finally {
    unlocking.value = false
  }
}

async function lockTerminal() {
  try {
    await api.post(`/api/servers/${props.serverId}/terminal/lock`)
  } catch (e) {}
  unlocked.value = false
  closeWs()
}

function initTerminal() {
  if (term) return
  if (!terminalContainer.value) return

  term = new Terminal({
    cursorBlink: true,
    fontFamily: '"JetBrains Mono", "Fira Code", monospace',
    fontSize: 13,
    lineHeight: 1.2,
    theme: {
      background: '#090d16',
      foreground: '#f8fafc',
      cursor: '#38bdf8',
      selectionBackground: 'rgba(56, 189, 248, 0.3)',
      black: '#111827',
      red: '#f87171',
      green: '#34d399',
      yellow: '#fbbf24',
      blue: '#38bdf8',
      magenta: '#c084fc',
      cyan: '#22d3ee',
      white: '#f8fafc',
    },
  })

  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(terminalContainer.value)
  fitAddon.fit()

  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'stdin', data }))
    }
  })

  window.addEventListener('resize', handleResize)
  connectWs()
}

function handleResize() {
  if (fitAddon && term) {
    fitAddon.fit()
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows,
      }))
    }
  }
}

function connectWs() {
  closeWs()
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/servers/${props.serverId}/terminal`

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    connected.value = true
    term.write('\r\n\x1b[1;36m[PANTAU PTY] Sesi terminal terhubung.\x1b[0m\r\n\r\n')
    handleResize()
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'stdout' && msg.data) {
        term.write(msg.data)
      } else if (msg.type === 'exit') {
        term.write('\r\n\x1b[1;33m[PANTAU PTY] Sesi ditutup oleh host.\x1b[0m\r\n')
        connected.value = false
      }
    } catch (e) {
      term.write(event.data)
    }
  }

  ws.onclose = () => {
    connected.value = false
    if (term) {
      term.write('\r\n\x1b[1;31m[PANTAU PTY] Sesi terputus.\x1b[0m\r\n')
    }
  }

  ws.onerror = (err) => {
    connected.value = false
  }
}

function closeWs() {
  if (ws) {
    ws.close()
    ws = null
  }
}

function reconnect() {
  if (term) term.clear()
  connectWs()
}

onMounted(() => {
  checkStatus()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  closeWs()
  if (term) {
    term.dispose()
    term = null
  }
})
</script>
