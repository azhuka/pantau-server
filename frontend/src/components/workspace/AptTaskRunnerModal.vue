<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[36000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="w-full max-w-4xl bg-[#070b16] border border-cyan-500/50 rounded-xl shadow-[0_24px_60px_rgba(0,0,0,0.92)] flex flex-col overflow-hidden font-mono text-xs">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 bg-[#0a101f] border-b border-cyan-500/30">
        <div class="flex items-center gap-2.5 min-w-0">
          <svg class="w-4 h-4 text-cyan-400 shrink-0" :class="status === 'running' ? 'animate-spin' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/>
          </svg>
          <span class="font-bold text-gray-100 truncate">{{ modalTitle }}</span>
          <span v-if="hostname" class="text-[11px] px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 shrink-0">{{ hostname }}</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span :class="badgeClass" class="px-2 py-0.5 rounded text-[11px] font-bold border">
            {{ statusLabel }}
          </span>
          <span class="px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-300 text-[11px] tabular-nums">
            {{ elapsedFormatted }}
          </span>
          <button
            type="button"
            @click="$emit('close')"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-white hover:bg-gray-800 cursor-pointer"
            title="Close (Task continues in background if running)"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- xterm.js Live Output Viewport -->
      <div class="bg-[#050811] p-2.5 h-[400px] overflow-hidden">
        <div ref="termContainerRef" class="w-full h-full"></div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between px-4 py-2.5 bg-[#0a101f] border-t border-cyan-500/20 gap-2">
        <span class="text-[11px] text-gray-400 truncate">{{ footerNote }}</span>
        <div class="flex items-center gap-2 shrink-0">
          <button
            v-if="status === 'failed' && canSuggestFix"
            type="button"
            @click="$emit('trigger-fix')"
            class="px-3 py-1.5 rounded bg-rose-700 hover:bg-rose-600 text-white font-bold text-xs cursor-pointer transition"
          >
            Repair Packages (APT Fix)
          </button>
          <button
            v-if="status === 'success' && taskUnit === 'APT_UPDATE' && upgradableCount > 0"
            type="button"
            @click="$emit('trigger-upgrade')"
            class="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs cursor-pointer transition flex items-center gap-1.5"
          >
            <span>Upgrade OS ({{ upgradableCount }})</span>
          </button>
          <button
            type="button"
            @click="$emit('close')"
            class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold text-xs cursor-pointer transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const props = defineProps({
  isOpen: Boolean,
  serverId: [Number, String],
  hostname: String,
  taskId: [Number, String],
  taskUnit: { type: String, default: 'APT_UPDATE' },
  taskDetail: { type: String, default: '' },
  startedAt: { type: [Number, String], default: null },
})

const emit = defineEmits(['close', 'completed', 'trigger-upgrade', 'trigger-fix'])

const termContainerRef = ref(null)
const status = ref('running') // running | success | warning | failed
const footerNote = ref('Dispatching command to remote agent...')
const upgradableCount = ref(0)
const canSuggestFix = ref(false)
const elapsedSec = ref(0)

let term = null
let fitAddon = null
let pollTimer = null
let secTimer = null
let lastRendered = ''

const modalTitle = computed(() => {
  if (props.taskUnit === 'APT_UPDATE') return 'Update OS Package Index'
  if (props.taskUnit === 'APT_UPGRADE' || props.taskUnit === 'APT_UPGRADE_INTERACT') return 'Upgrade OS Packages'
  if (props.taskUnit === 'APT_FIX') return 'Repair OS Packages (dpkg / apt fix)'
  if (props.taskUnit === 'PKG_UPGRADE') return `Upgrade Package: ${props.taskDetail || ''}`
  if (props.taskUnit === 'PKG_CLEAN') return 'Clean Package Cache'
  return 'OS Package Task'
})

const statusLabel = computed(() => {
  if (status.value === 'running') return 'Running'
  if (status.value === 'success') return 'Completed'
  if (status.value === 'warning') return 'Warning'
  return 'Failed'
})

const badgeClass = computed(() => {
  if (status.value === 'running') return 'bg-cyan-950/80 text-cyan-300 border-cyan-600/60'
  if (status.value === 'success') return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60'
  if (status.value === 'warning') return 'bg-amber-950/80 text-amber-300 border-amber-600/60'
  return 'bg-rose-950/80 text-rose-300 border-rose-600/60'
})

const elapsedFormatted = computed(() => {
  const m = Math.floor(elapsedSec.value / 60)
  const s = elapsedSec.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function initTerminal() {
  if (term) {
    term.dispose()
    term = null
  }
  if (!termContainerRef.value) return
  term = new Terminal({
    convertEol: true,
    disableStdin: true,
    cursorBlink: false,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', Menlo, Monaco, Consolas, monospace",
    theme: { background: '#050811', foreground: '#e2e8f0' },
  })
  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(termContainerRef.value)
  fitAddon.fit()
  term.writeln(`\x1b[36m── ${modalTitle.value} (${props.hostname || 'Host'}) ──\x1b[0m\r\n`)
}

function writeSnapshot(text) {
  if (!term || !text || text === lastRendered) return
  lastRendered = text
  term.reset()
  term.writeln(`\x1b[36m── ${modalTitle.value} (${props.hostname || 'Host'}) ──\x1b[0m\r\n`)
  term.write(text)
}

function stopTimers() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (secTimer) { clearInterval(secTimer); secTimer = null }
}

async function pollTask() {
  if (!props.taskId) return
  const token = localStorage.getItem('pantau_token') || ''
  try {
    const res = await fetch(`/api/logs/request/${props.taskId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) return

    if (data.status === 'pending') {
      footerNote.value = 'Waiting for remote agent to pick up task...'
      return
    }
    if (data.status === 'executing') {
      footerNote.value = 'Streaming live package manager output...'
      if (data.result) writeSnapshot(data.result)
      return
    }

    stopTimers()
    let parsed = null
    if (typeof data.result === 'string' && data.result.trim().startsWith('{')) {
      try { parsed = JSON.parse(data.result) } catch (_) {}
    }

    const finalOut = parsed?.output || (typeof data.result === 'string' ? data.result : '')
    if (finalOut) writeSnapshot(finalOut)

    if (data.status === 'success') {
      upgradableCount.value = Number(parsed?.apt?.upgradable || 0)
      if (parsed?.warning || parsed?.has_fetch_err) {
        status.value = 'warning'
        footerNote.value = parsed.warning || parsed.fetch_err_reason || 'Completed with repository warnings.'
      } else {
        status.value = 'success'
        footerNote.value = props.taskUnit === 'APT_UPDATE'
          ? (upgradableCount.value > 0 ? `${upgradableCount.value} package(s) available for upgrade.` : 'All OS packages are up-to-date.')
          : 'OS package operation completed successfully.'
      }
      emit('completed', { ok: true, unit: props.taskUnit, apt: parsed?.apt || null })
    } else {
      status.value = 'failed'
      const low = (finalOut || '').toLowerCase()
      canSuggestFix.value = props.taskUnit !== 'APT_FIX' && (low.includes('dpkg --configure -a') || low.includes('fix-broken') || low.includes('unmet dependencies'))
      const errLine = (finalOut || '').split('\n').map(l => l.trim()).reverse().find(l => /^e:\s+/i.test(l) || /^error:\s+/i.test(l))
      footerNote.value = parsed?.error || (errLine ? errLine.replace(/^e:\s+/i, '') : 'OS package operation failed.')
      emit('completed', { ok: false, unit: props.taskUnit, apt: parsed?.apt || null })
    }
  } catch (_) {}
}

function computeElapsed() {
  if (!props.startedAt) return 0
  const ms = typeof props.startedAt === 'number' ? props.startedAt : Date.parse(String(props.startedAt).endsWith('Z') ? props.startedAt : `${props.startedAt}Z`)
  if (!ms || Number.isNaN(ms)) return 0
  return Math.max(0, Math.floor((Date.now() - ms) / 1000))
}

watch(
  () => [props.isOpen, props.taskId],
  ([open, rid]) => {
    stopTimers()
    if (open && rid) {
      status.value = 'running'
      upgradableCount.value = 0
      canSuggestFix.value = false
      elapsedSec.value = computeElapsed()
      lastRendered = ''
      footerNote.value = 'Dispatching command to remote agent...'
      nextTick(() => {
        initTerminal()
        pollTask()
        pollTimer = setInterval(pollTask, 800)
        secTimer = setInterval(() => {
          elapsedSec.value = props.startedAt ? computeElapsed() : (elapsedSec.value + 1)
        }, 1000)
      })
    } else if (!open && term) {
      term.dispose()
      term = null
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  stopTimers()
  if (term) { term.dispose(); term = null }
})
</script>
