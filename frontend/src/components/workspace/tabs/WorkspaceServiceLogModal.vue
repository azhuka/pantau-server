<template>
  <Teleport to="body">
    <div v-if="target" @click.self="$emit('close')" class="fixed inset-0 z-[100020] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 font-mono">
      <div class="w-full max-w-5xl max-h-[85vh] flex flex-col rounded-xl bg-[#070c18] border border-cyan-500/40 shadow-2xl overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-cyan-500/20 bg-[#050811] flex-wrap gap-2">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
            <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider">
              Service Logs: <span class="text-cyan-300">{{ displayTitle }}</span>
            </h3>
            <span v-if="target.status" class="px-2 py-0.5 rounded text-[10px] uppercase font-bold" :class="statusBadgeClass">
              {{ target.status }}
            </span>
            <span v-if="target.port" class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
              Port {{ target.port }}
            </span>
            <span v-if="pollStatus" class="text-[11px] text-amber-300">{{ pollStatus }}</span>
          </div>

          <div class="flex items-center gap-1.5">
            <button
              type="button"
              @click="fetchLogs"
              :disabled="fetching || !serverOnline"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="serverOnline ? 'Refresh log output' : 'Host is offline'"
            >
              <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': fetching }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
            <button
              type="button"
              @click="downloadLogs"
              :disabled="filteredLines.length === 0"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              title="Download visible log lines (.log)"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <button
              type="button"
              @click="$emit('close')"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-rose-950 border border-gray-700 text-gray-400 hover:text-rose-300 inline-flex items-center justify-center cursor-pointer"
              title="Close service log console"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>

        <!-- Contextual Log Sources Bar -->
        <div class="px-4 py-2.5 border-b border-gray-800/80 bg-[#060a14] flex items-center gap-2 flex-wrap">
          <span class="text-[10px] uppercase font-bold text-gray-400 tracking-wider">Sources:</span>
          <button
            v-for="src in contextualSources"
            :key="src.id"
            type="button"
            @click="selectSource(src.id)"
            class="px-2.5 py-1 rounded text-[11px] font-semibold border transition cursor-pointer"
            :class="selectedSource === src.id ? 'bg-cyan-950 text-cyan-200 border-cyan-500/60' : 'bg-gray-900 text-gray-400 border-gray-700 hover:text-white'"
            :title="src.desc"
          >
            {{ src.label }}
          </button>
        </div>

        <!-- Filter Controls -->
        <div class="px-4 py-2 border-b border-gray-800/80 flex items-center justify-between flex-wrap gap-2 text-xs">
          <div class="flex items-center gap-2 flex-wrap">
            <select v-model.number="lineLimit" @change="fetchLogs" class="noc-filter-select">
              <option :value="50">50 Lines</option>
              <option :value="100">100 Lines</option>
              <option :value="200">200 Lines</option>
              <option :value="500">500 Lines</option>
              <option :value="1000">1000 Lines</option>
            </select>
            <select v-model="levelFilter" class="noc-filter-select">
              <option value="all">All Levels</option>
              <option value="err">Error / Critical</option>
              <option value="warn">Warning</option>
              <option value="http_err">HTTP 4xx / 5xx</option>
              <option value="info">Info / Notice</option>
            </select>
            <div class="noc-filter-search-box">
              <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input v-model="search" type="search" placeholder="Filter log lines..." />
            </div>
          </div>
          <span class="text-[11px] text-gray-400">{{ filteredLines.length }} / {{ rawLines.length }} lines</span>
        </div>

        <!-- Log Viewport -->
        <div class="flex-1 overflow-y-auto bg-[#050811] p-2">
          <div v-if="filteredLines.length === 0" class="py-12 text-center text-xs text-gray-400">
            {{ fetching ? 'Streaming contextual logs from Pantau Agent...' : (rawLines.length === 0 ? 'No log entries returned for this source.' : 'No log lines match the active filter.') }}
          </div>
          <div v-for="entry in filteredLines" :key="entry.num" class="noc-log-row">
            <div class="noc-log-num">{{ entry.num }}</div>
            <div class="noc-log-line" :class="lineColorClass(entry.text)">{{ entry.text }}</div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'

const props = defineProps({
  serverId: { type: [Number, String], default: null },
  serverOnline: { type: Boolean, default: false },
  target: { type: Object, default: null }, // { unit, processName, status, port }
  availableLogs: { type: Array, default: () => [] },
})

defineEmits(['close'])

const selectedSource = ref('')
const lineLimit = ref(200)
const levelFilter = ref('all')
const search = ref('')
const rawLogText = ref('')
const fetching = ref(false)
const pollStatus = ref('')
let pollCancelled = false

const cleanUnit = computed(() => String(props.target?.unit || '').replace(/\.service$/, '').trim())
const cleanProc = computed(() => String(props.target?.processName || '').replace(/\.service$/, '').trim())

const displayTitle = computed(() => {
  if (!cleanUnit.value) return ''
  if (cleanProc.value && cleanProc.value !== cleanUnit.value) return `${cleanUnit.value}.service (${cleanProc.value})`
  return `${cleanUnit.value}.service`
})

const statusBadgeClass = computed(() => {
  const s = String(props.target?.status || '').toLowerCase()
  if (s === 'running' || s === 'up' || s === 'active') return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  if (s === 'failed' || s === 'down') return 'bg-rose-950 text-rose-300 border border-rose-800'
  return 'bg-gray-800 text-gray-300 border border-gray-700'
})

const contextualSources = computed(() => {
  if (!cleanUnit.value) return []
  const sources = []
  const seen = new Set()

  sources.push({
    id: cleanUnit.value,
    label: `Systemd Journal (${cleanUnit.value})`,
    desc: `journalctl -u ${cleanUnit.value}`,
  })
  seen.add(cleanUnit.value.toUpperCase())

  if (cleanProc.value && cleanProc.value !== cleanUnit.value && !seen.has(cleanProc.value.toUpperCase())) {
    sources.push({
      id: cleanProc.value,
      label: `Process Journal (${cleanProc.value})`,
      desc: `journalctl _COMM=${cleanProc.value}`,
    })
    seen.add(cleanProc.value.toUpperCase())
  }

  const tokens = [cleanUnit.value.toLowerCase(), cleanProc.value.toLowerCase()].filter(Boolean)
  for (const src of props.availableLogs || []) {
    const sid = String(src.id || '')
    if (!sid || seen.has(sid.toUpperCase())) continue
    const hay = `${sid} ${src.name || ''} ${src.desc || ''}`.toLowerCase()
    if (tokens.some(tk => hay.includes(tk))) {
      sources.push({ id: sid, label: src.name || sid, desc: src.desc || sid })
      seen.add(sid.toUpperCase())
    }
  }
  return sources
})

watch(() => props.target, (val) => {
  pollCancelled = true
  rawLogText.value = ''
  pollStatus.value = ''
  levelFilter.value = 'all'
  search.value = ''
  if (val && cleanUnit.value) {
    selectedSource.value = cleanUnit.value
    fetchLogs()
  }
})

function selectSource(srcId) {
  selectedSource.value = srcId
  fetchLogs()
}

const rawLines = computed(() => {
  if (!rawLogText.value) return []
  return rawLogText.value.split('\n').filter((l, i, arr) => !(i === arr.length - 1 && l === ''))
})

const filteredLines = computed(() => {
  const q = search.value.toLowerCase().trim()
  const lvl = levelFilter.value
  const out = []
  rawLines.value.forEach((line, idx) => {
    const low = line.toLowerCase()
    if (lvl === 'err' && !(low.includes('err') || low.includes('crit') || low.includes('emerg') || low.includes('fatal') || low.includes('panic') || /\b5\d\d\b/.test(line))) return
    if (lvl === 'warn' && !(low.includes('warn') || /\b4\d\d\b/.test(line))) return
    if (lvl === 'http_err' && !/\b(4\d\d|5\d\d)\b/.test(line)) return
    if (lvl === 'info' && !(low.includes('info') || low.includes('notice') || /\b(200|201|204)\b/.test(line))) return
    if (q && !low.includes(q)) return
    out.push({ num: idx + 1, text: line })
  })
  return out
})

function lineColorClass(line) {
  const l = line.toLowerCase()
  if (l.includes('err') || l.includes('crit') || l.includes('fatal') || l.includes('panic')) return 'text-rose-300'
  if (l.includes('warn')) return 'text-amber-300'
  return 'text-gray-300'
}

async function fetchLogs() {
  if (!props.serverId || !props.serverOnline || !selectedSource.value) return
  pollCancelled = true
  await new Promise(r => setTimeout(r, 20))
  pollCancelled = false
  fetching.value = true
  pollStatus.value = 'Requesting logs...'
  const token = localStorage.getItem('pantau_token')
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  try {
    const res = await fetch('/api/logs/request', {
      method: 'POST',
      headers,
      body: JSON.stringify({ server_id: props.serverId, unit: selectedSource.value, lines: lineLimit.value }),
    })
    const data = await res.json()
    if (!res.ok || !data.id) { pollStatus.value = data.detail || 'Request failed'; return }
    const deadline = Date.now() + 25000
    while (!pollCancelled && Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 1000))
      if (pollCancelled) break
      const pRes = await fetch(`/api/logs/request/${data.id}`, { headers: { Authorization: `Bearer ${token}` } })
      const pData = await pRes.json()
      if (pData.status === 'success') { rawLogText.value = pData.result || ''; pollStatus.value = ''; break }
      if (pData.status === 'failed') { pollStatus.value = pData.result || 'Agent failed to read logs'; break }
      pollStatus.value = pData.status === 'executing' ? 'Reading journal...' : 'Queued...'
    }
  } catch (e) {
    pollStatus.value = 'Network error'
  } finally {
    fetching.value = false
  }
}

function downloadLogs() {
  const blob = new Blob([filteredLines.value.map(x => x.text).join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `server-${props.serverId}-${selectedSource.value}.log`
  a.click()
  URL.revokeObjectURL(url)
}

onUnmounted(() => { pollCancelled = true })
</script>
