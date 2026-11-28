<template>
  <Teleport to="body">
    <div v-if="pkgName" class="fixed inset-0 z-[100020] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 font-mono">
      <div class="w-full max-w-4xl max-h-[82vh] flex flex-col rounded-xl bg-[#070c18] border border-cyan-500/40 shadow-2xl overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b border-cyan-500/20 bg-[#050811] gap-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="w-2 h-2 rounded-full bg-cyan-400 shrink-0"></span>
            <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider truncate">
              Package History Logs: <span class="text-cyan-300">{{ pkgName }}</span>
            </h3>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              @click="fetchLogs"
              :disabled="loading || !isOnline"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="isOnline ? 'Refresh package logs' : 'Asset is offline'"
            >
              <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
            <button
              type="button"
              @click="copyLogs"
              :disabled="!logText"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="copied ? 'Copied!' : 'Copy logs to clipboard'"
            >
              <svg v-if="!copied" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              <svg v-else class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </button>
            <button
              type="button"
              @click="$emit('close')"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-rose-950 border border-gray-700 text-gray-300 hover:text-rose-300 inline-flex items-center justify-center cursor-pointer"
              title="Close"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-auto p-4 bg-[#03060d] text-[11px] leading-relaxed text-gray-300 whitespace-pre-wrap select-text">
          <div v-if="loading && !logText" class="text-cyan-400">Querying dpkg / apt history for {{ pkgName }}...</div>
          <div v-else-if="errorMsg" class="text-rose-400">{{ errorMsg }}</div>
          <template v-else>{{ logText }}</template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  serverId: { type: Number, default: null },
  pkgName: { type: String, default: '' },
  isOnline: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const logText = ref('')
const errorMsg = ref('')
const copied = ref(false)

async function fetchLogs() {
  if (!props.pkgName || !props.serverId) return
  if (!props.isOnline) {
    errorMsg.value = 'Asset is offline; unable to query live package logs.'
    return
  }
  loading.value = true
  errorMsg.value = ''
  logText.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch('/api/logs/request', {
      method: 'POST',
      headers,
      body: JSON.stringify({ server_id: props.serverId, unit: 'PKG_LOGS', detail: props.pkgName, lines: 150 }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)

    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 500))
      const poll = await fetch(`/api/logs/request/${data.id}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      const pData = await poll.json().catch(() => ({}))
      if (pData.status === 'success') {
        logText.value = pData.result || `No dpkg/apt log entries found for ${props.pkgName}.`
        return
      }
      if (pData.status === 'failed') {
        throw new Error(pData.result || 'Failed to read package logs')
      }
    }
    throw new Error('Timed out waiting for agent response')
  } catch (err) {
    errorMsg.value = err.message || 'Failed to load package logs'
  } finally {
    loading.value = false
  }
}

async function copyLogs() {
  if (!logText.value) return
  try {
    await navigator.clipboard.writeText(logText.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {}
}

function onKey(e) {
  if (e.key === 'Escape' && props.pkgName) emit('close')
}

watch(() => props.pkgName, (val) => {
  if (val) fetchLogs()
  else { logText.value = ''; errorMsg.value = '' }
})

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>
