<template>
  <Teleport to="body">
    <div v-if="target" @click.self="$emit('close')" class="fixed inset-0 z-[100020] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 font-mono">
      <div class="w-full max-w-5xl max-h-[85vh] flex flex-col rounded-xl bg-[#070c18] border border-cyan-500/40 shadow-2xl overflow-hidden">
        <!-- 1. Header: Identity + Live Tail, Refresh, Copy, Download, Open in Logs Tab, Close -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-cyan-500/20 bg-[#050811] flex-wrap gap-2">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="w-2 h-2 rounded-full" :class="liveTail && serverOnline ? 'bg-emerald-400 beacon-live' : 'bg-gray-500'"></span>
            <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider">
              Service Logs: <span class="text-cyan-300">{{ displayTitle }}</span>
            </h3>
            <span v-if="target.status" class="px-2 py-0.5 rounded text-[10px] uppercase font-bold" :class="statusBadgeClass">
              {{ target.status }}
            </span>
            <span v-if="target.port" class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
              Port {{ target.port }}
            </span>
          </div>

          <div class="flex items-center gap-1.5 flex-wrap">
            <!-- Live Tail Toggle -->
            <button
              type="button"
              @click="toggleLiveTail"
              class="px-2.5 h-[26px] rounded border text-[11px] font-bold inline-flex items-center gap-1.5 cursor-pointer transition"
              :class="liveTail ? 'bg-emerald-950/70 border-emerald-600/60 text-emerald-300' : 'bg-gray-900 border-gray-700 text-gray-400 hover:text-white'"
              title="Toggle automatic Live Tail (4s interval)"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="liveTail ? 'bg-emerald-400' : 'bg-gray-500'"></span>
              <span>Live Tail: {{ liveTail ? 'ON' : 'PAUSED' }}</span>
            </button>

            <!-- Refresh -->
            <button
              type="button"
              @click="fetchLogs(false)"
              :disabled="fetching || !serverOnline"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="serverOnline ? 'Refresh log output now' : 'Host is offline'"
            >
              <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': fetching }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>

            <!-- Copy Raw Logs -->
            <button
              type="button"
              @click="copyLogs"
              :disabled="filteredLines.length === 0"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="copied ? 'Copied to clipboard!' : 'Copy visible logs to clipboard'"
            >
              <svg v-if="!copied" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              <svg v-else class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </button>

            <!-- Download -->
            <button
              type="button"
              @click="downloadLogs"
              :disabled="filteredLines.length === 0"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              title="Download visible log lines (.log)"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>

            <!-- Open in Full Logs Tab -->
            <button
              type="button"
              @click="openInFullTab"
              class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer"
              title="Open in full Logs tab"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </button>

            <!-- Close -->
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

        <!-- 2. Contextual Log Sources Bar -->
        <div v-if="contextualSources.length > 1" class="px-4 py-2 border-b border-gray-800/80 bg-[#060a14] flex items-center gap-2 flex-wrap">
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

        <!-- 3. Filter Controls -->
        <div class="px-4 py-2 border-b border-gray-800/80 flex items-center justify-between flex-wrap gap-2 text-xs">
          <div class="flex items-center gap-2 flex-wrap">
            <select v-model.number="lineLimit" @change="fetchLogs(false)" class="noc-filter-select">
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
          <span class="text-[11px] text-cyan-300">{{ filteredLines.length }} / {{ rawLines.length }} lines</span>
        </div>

        <!-- 4. Log Viewport -->
        <div ref="viewportRef" @scroll="handleScroll" class="flex-1 overflow-y-auto bg-[#050811] p-2 min-h-[280px]">
          <div v-if="filteredLines.length === 0" class="py-12 text-center text-xs text-gray-400">
            {{ fetching ? 'Streaming contextual logs from Pantau Agent...' : (rawLines.length === 0 ? 'No log entries returned for this source.' : 'No log lines match the active filter.') }}
          </div>
          <div v-for="entry in filteredLines" :key="entry.num" class="noc-log-row">
            <div class="noc-log-num">{{ entry.num }}</div>
            <div class="noc-log-line" :class="lineColorClass(entry.text)">{{ entry.text }}</div>
          </div>
        </div>

        <!-- 5. Statusbar Footer -->
        <div class="px-4 py-2 border-t border-cyan-500/20 bg-[#050811] flex items-center justify-between flex-wrap gap-2 text-[11px] text-gray-400">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="w-2 h-2 rounded-full" :class="fetching ? 'bg-amber-400' : 'bg-emerald-400'"></span>
            <span class="font-semibold text-gray-200">{{ pollStatus || (liveTail ? 'Ready' : 'Paused') }}</span>
            <span>·</span>
            <span>{{ filteredLines.length }} lines</span>
            <span>·</span>
            <span>Target: <strong class="text-cyan-300">{{ activeSourceDesc }}</strong></span>
          </div>
          <div class="flex items-center gap-2.5">
            <button
              v-if="userScrolledUp"
              type="button"
              @click="jumpToLatest"
              class="px-2 py-0.5 rounded bg-cyan-950/70 border border-cyan-500/40 text-cyan-300 hover:text-white text-[10px] font-bold cursor-pointer"
            >
              ↓ Jump to Latest
            </button>
            <span class="text-gray-500">Auto Tail 4s</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  serverId: { type: [Number, String], default: null },
  serverOnline: { type: Boolean, default: false },
  target: { type: Object, default: null }, // { unit, processName, status, port }
  availableLogs: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'open-full-tab'])

const viewportRef = ref(null)
const selectedSource = ref('')
const lineLimit = ref(200)
const levelFilter = ref('all')
const search = ref('')
const rawLogText = ref('')
const fetching = ref(false)
const pollStatus = ref('')
const liveTail = ref(true)
const userScrolledUp = ref(false)
const copied = ref(false)

let pollCancelled = false
let tailTimer = null

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

  sources.push({ id: cleanUnit.value, label: `Systemd Journal (${cleanUnit.value})`, desc: `journalctl -u ${cleanUnit.value}` })
  seen.add(cleanUnit.value.toUpperCase())

  if (cleanProc.value && cleanProc.value !== cleanUnit.value && !seen.has(cleanProc.value.toUpperCase())) {
    sources.push({ id: cleanProc.value, label: `Process Journal (${cleanProc.value})`, desc: `journalctl _COMM=${cleanProc.value}` })
    seen.add(cleanProc.value.toUpperCase())
  }

  // Smart alias & token matching matching mature NOC blueprint
  const tokens = new Set()
  for (const raw of [cleanUnit.value.toLowerCase(), cleanProc.value.toLowerCase()]) {
    if (!raw) continue
    tokens.add(raw)
    if (raw.endsWith('d') && raw.length > 3) tokens.add(raw.slice(0, -1))
    raw.split(/[-_]/).forEach(p => { if (p.length > 2) tokens.add(p) })
  }
  if (tokens.has('mysql') || tokens.has('mariadb')) { tokens.add('mysql'); tokens.add('mariadb') }
  if (tokens.has('apache') || tokens.has('apache2') || tokens.has('httpd')) { tokens.add('apache'); tokens.add('apache2'); tokens.add('httpd') }
  if (tokens.has('ssh') || tokens.has('sshd')) { tokens.add('auth'); tokens.add('ssh'); tokens.add('sshd') }

  for (const src of props.availableLogs || []) {
    const sid = String(src.id || '')
    if (!sid || seen.has(sid.toUpperCase())) continue
    const hay = `${sid} ${src.name || ''} ${src.desc || src.path || ''} ${src.group || ''}`.toLowerCase()
    if ([...tokens].some(tk => hay.includes(tk))) {
      sources.push({ id: sid, label: src.name || sid, desc: src.desc || src.path || sid })
      seen.add(sid.toUpperCase())
    }
  }
  return sources
})

const activeSourceDesc = computed(() => {
  const found = contextualSources.value.find(s => s.id === selectedSource.value)
  return found?.desc || selectedSource.value || '-'
})

function stopTailTimer() {
  if (tailTimer) { clearTimeout(tailTimer); tailTimer = null }
}

function scheduleNextTail() {
  stopTailTimer()
  if (!props.target || !liveTail.value || !props.serverOnline) return
  tailTimer = setTimeout(() => {
    if (props.target && liveTail.value && !document.hidden) fetchLogs(true)
  }, 4000)
}

watch(() => props.target, (val) => {
  pollCancelled = true
  stopTailTimer()
  rawLogText.value = ''
  pollStatus.value = ''
  levelFilter.value = 'all'
  search.value = ''
  userScrolledUp.value = false
  liveTail.value = true
  if (val && cleanUnit.value) {
    selectedSource.value = cleanUnit.value
    fetchLogs(false)
  }
})

function selectSource(srcId) {
  selectedSource.value = srcId
  rawLogText.value = ''
  fetchLogs(false)
}

function toggleLiveTail() {
  liveTail.value = !liveTail.value
  if (liveTail.value) {
    userScrolledUp.value = false
    fetchLogs(true)
  } else {
    stopTailTimer()
  }
}

function handleScroll() {
  const el = viewportRef.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 28
  if (!atBottom && liveTail.value) {
    userScrolledUp.value = true
    liveTail.value = false
    stopTailTimer()
  } else if (atBottom) {
    userScrolledUp.value = false
  }
}

async function jumpToLatest() {
  userScrolledUp.value = false
  liveTail.value = true
  await nextTick()
  if (viewportRef.value) viewportRef.value.scrollTop = viewportRef.value.scrollHeight
  scheduleNextTail()
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

async function fetchLogs(isTail) {
  if (!props.serverId || !props.serverOnline || !selectedSource.value) return
  if (fetching.value && isTail) return
  pollCancelled = true
  stopTailTimer()
  await new Promise(r => setTimeout(r, 20))
  pollCancelled = false
  fetching.value = true
  pollStatus.value = isTail ? 'Tail polling...' : 'Requesting logs...'
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
      if (pData.status === 'success') {
        rawLogText.value = pData.result || ''
        pollStatus.value = ''
        if (!userScrolledUp.value) {
          await nextTick()
          if (viewportRef.value) viewportRef.value.scrollTop = viewportRef.value.scrollHeight
        }
        break
      }
      if (pData.status === 'failed') { pollStatus.value = pData.result || 'Agent failed to read logs'; break }
      pollStatus.value = pData.status === 'executing' ? 'Reading journal...' : 'Queued...'
    }
  } catch (e) {
    pollStatus.value = 'Network error'
  } finally {
    fetching.value = false
    scheduleNextTail()
  }
}

async function copyLogs() {
  const txt = filteredLines.value.map(x => x.text).join('\n')
  if (!txt) return
  try {
    await navigator.clipboard.writeText(txt)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    console.error('Clipboard copy failed:', e)
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

function openInFullTab() {
  const src = selectedSource.value || cleanUnit.value
  stopTailTimer()
  pollCancelled = true
  emit('open-full-tab', src)
}

onUnmounted(() => {
  pollCancelled = true
  stopTailTimer()
})
</script>
