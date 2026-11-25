<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>

    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">// SYSTEM JOURNAL &amp; LOG STREAM</h3>
        <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-[#060a14] border border-gray-800 text-cyan-300">{{ selectedSource }}</span>
        <span v-if="pollStatus" class="text-[11px] text-amber-300">{{ pollStatus }}</span>
      </div>
      <div class="flex items-center gap-1.5">
        <button type="button" @click="fetchOnDemandLogs" :disabled="fetching || !serverOnline" class="w-[26px] h-[26px] p-0 flex items-center justify-center rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 transition cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed" :title="serverOnline ? 'Refresh log output from agent' : 'Host is offline'">
          <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': fetching }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        </button>
        <button type="button" @click="downloadLogs" :disabled="filteredLines.length === 0" class="w-[26px] h-[26px] p-0 flex items-center justify-center rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 transition cursor-pointer disabled:opacity-35 disabled:cursor-not-allowed" title="Download visible log lines (.log)">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
      </div>
    </div>

    <NocFilterPanel
      :has-active-filters="Boolean(levelFilter !== 'all' || search.trim())"
      :summary-text="`${filteredLines.length} / ${rawLines.length} lines`"
      compact
      @reset="levelFilter = 'all'; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col" style="min-width:210px;max-width:300px">
          <label class="noc-filter-label" for="log-unit-select">{{ t('flt_log_source') }}</label>
          <select id="log-unit-select" v-model="selectedSource" @change="fetchOnDemandLogs" class="noc-filter-select w-full">
            <optgroup v-for="(items, grp) in groupedSources" :key="grp" :label="grp">
              <option v-for="src in items" :key="src.id" :value="src.id">
                {{ src.name }} ({{ src.desc || src.id }})
              </option>
            </optgroup>
          </select>
        </div>

        <div class="noc-filter-col">
          <label class="noc-filter-label" for="log-lines-select">{{ t('flt_log_lines') }}</label>
          <select id="log-lines-select" v-model.number="lineLimit" @change="fetchOnDemandLogs" class="noc-filter-select">
            <option :value="50">50 Lines</option>
            <option :value="100">100 Lines</option>
            <option :value="200">200 Lines</option>
            <option :value="500">500 Lines</option>
            <option :value="1000">1000 Lines</option>
          </select>
        </div>

        <div class="noc-filter-col">
          <label class="noc-filter-label" for="log-level-select">{{ t('flt_log_level') }}</label>
          <select id="log-level-select" v-model="levelFilter" class="noc-filter-select">
            <option value="all">All Levels</option>
            <option value="err">Error / Critical</option>
            <option value="warn">Warning</option>
            <option value="http_err">HTTP 4xx / 5xx</option>
            <option value="info">Info / Notice</option>
          </select>
        </div>

        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="log-keyword-input">{{ t('flt_log_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="log-keyword-input" v-model="search" type="search" placeholder="Filter lines by keyword..." />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <!-- Precision Row-by-Row Log Viewport (Zero-Fake Data) -->
    <div class="bg-[#050811] border border-cyan-900/60 rounded-lg max-h-[430px] overflow-y-auto">
      <div v-if="filteredLines.length === 0" class="py-10 px-4 text-center text-xs text-gray-400">
        {{ fetching ? 'Polling real-time logs from Pantau Agent...' : (rawLines.length === 0 ? 'Select a log source or click Refresh to stream logs from host.' : 'No log lines match the active level/keyword filter.') }}
      </div>
      <div v-for="entry in filteredLines" :key="entry.num" class="noc-log-row">
        <div class="noc-log-num">{{ entry.num }}</div>
        <div class="noc-log-line" :class="lineColorClass(entry.text)">{{ entry.text }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'

const { t } = useI18n()

const props = defineProps({
  serverId: { type: Number, default: null },
  serverOnline: { type: Boolean, default: false },
  logsList: { type: Array, default: () => [] },
  availableLogs: { type: Array, default: () => [] },
})

const selectedSource = ref('SYSTEM_ERRORS')
const lineLimit = ref(200)
const levelFilter = ref('all')
const search = ref('')
const rawLogText = ref('')
const fetching = ref(false)
const pollStatus = ref('')
let pollCancelled = false

const groupedSources = computed(() => {
  const groups = {}
  const list = props.availableLogs?.length
    ? props.availableLogs
    : [{ id: 'SYSTEM_ERRORS', group: 'System & Security', name: 'System Critical Errors', desc: 'journalctl -p 0..3' }, { id: 'AUTH', group: 'System & Security', name: 'Auth Log', desc: '/var/log/auth.log' }, { id: 'SYSLOG', group: 'System & Security', name: 'Syslog', desc: '/var/log/syslog' }]
  for (const s of list) {
    const g = s.group || 'System'
    if (!groups[g]) groups[g] = []
    groups[g].push(s)
  }
  return groups
})

watch(() => props.availableLogs, (list) => {
  if (Array.isArray(list) && list.length && !list.some(s => s.id === selectedSource.value)) {
    selectedSource.value = list[0].id
  }
}, { immediate: true })

const rawLines = computed(() => {
  if (rawLogText.value) {
    return rawLogText.value.split('\n').filter((l, i, arr) => !(i === arr.length - 1 && l === ''))
  }
  return (props.logsList || []).map(item => typeof item === 'string' ? item : `[${item.time || '-'}] ${item.unit || ''} ${item.msg || item.message || JSON.stringify(item)}`)
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

async function fetchOnDemandLogs() {
  if (!props.serverId || !props.serverOnline || fetching.value) return
  fetching.value = true
  pollStatus.value = 'Dispatching log request...'
  pollCancelled = false
  const token = localStorage.getItem('pantau_token')
  const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
  try {
    const res = await fetch('/api/logs/request', {
      method: 'POST', headers,
      body: JSON.stringify({ server_id: props.serverId, unit: selectedSource.value, lines: lineLimit.value })
    })
    const data = await res.json()
    if (!res.ok || !data.id) { pollStatus.value = data.detail || 'Request failed'; return }
    const deadline = Date.now() + 25000
    while (!pollCancelled && Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 1200))
      const pRes = await fetch(`/api/logs/request/${data.id}`, { headers: { Authorization: `Bearer ${token}` } })
      const pData = await pRes.json()
      if (pData.status === 'success') { rawLogText.value = pData.result || ''; pollStatus.value = ''; break }
      if (pData.status === 'failed') { pollStatus.value = pData.result || 'Agent failed to read log'; break }
      pollStatus.value = pData.status === 'executing' ? 'Reading log file...' : 'Queued for agent...'
    }
  } catch (e) { pollStatus.value = 'Network error' } finally { fetching.value = false }
}

function downloadLogs() {
  const blob = new Blob([filteredLines.value.map(x => x.text).join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `server-${props.serverId || 'host'}-${selectedSource.value}.log`; a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => { if (props.serverId && props.serverOnline && rawLines.value.length === 0) fetchOnDemandLogs() })
onUnmounted(() => { pollCancelled = true })
</script>
