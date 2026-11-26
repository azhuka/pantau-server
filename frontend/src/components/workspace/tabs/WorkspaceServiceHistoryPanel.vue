<template>
  <div class="hud-tactical-card rounded-xl p-4 space-y-3 font-mono border border-cyan-500/30">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        <h4 class="text-xs font-bold text-gray-100 uppercase tracking-wider">
          Service History: <span class="text-cyan-300">{{ serviceName }}</span>
        </h4>
        <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="uptimeBadgeClass">
          {{ uptimePct !== null ? `${uptimePct}% uptime` : 'No data' }}
        </span>
      </div>

      <div class="flex items-center gap-2">
        <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-[11px]">
          <button
            v-for="r in ranges"
            :key="r.id"
            type="button"
            @click="selectedRange = r.id"
            class="px-2 py-0.5 rounded transition cursor-pointer"
            :class="selectedRange === r.id ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'"
          >
            {{ r.label }}
          </button>
        </div>
        <button
          type="button"
          @click="$emit('close')"
          class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-gray-800 border border-gray-700 text-gray-400 hover:text-white inline-flex items-center justify-center cursor-pointer"
          title="Close service history"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>

    <div v-if="loading" class="py-6 text-center text-xs text-gray-400">Loading service history...</div>
    <div v-else-if="points.length === 0" class="py-6 text-center text-xs text-gray-500 italic">
      No metric samples recorded for this time range yet.
    </div>
    <template v-else>
      <div class="flex items-center justify-between text-[11px] text-gray-400 flex-wrap gap-2">
        <div>
          Current: <span class="font-bold uppercase" :class="nowStatus === 'up' ? 'text-emerald-400' : 'text-rose-400'">{{ nowStatus }}</span>
          · Connections: <span class="text-gray-200 font-semibold">{{ nowConns }}</span>
          · Response: <span class="text-gray-200 font-semibold">{{ nowRt !== null ? `${nowRt} ms` : '-' }}</span>
        </div>
        <div class="flex items-center gap-3 text-[10px]">
          <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-emerald-500"></span> Up</span>
          <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-rose-500"></span> Down</span>
          <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-gray-600"></span> No Data</span>
        </div>
      </div>

      <!-- Uptime Strip -->
      <div class="flex items-center gap-[2px] h-5 bg-[#060a14] p-1 rounded border border-gray-800/80 overflow-hidden">
        <div
          v-for="(pt, idx) in points"
          :key="idx"
          class="flex-1 h-full rounded-[1px] transition-opacity hover:opacity-80"
          :class="stripColor(pt)"
          :title="`${formatTs(pt.t)} — Uptime: ${pt.up_ratio !== null ? Math.round(pt.up_ratio * 100) + '%' : 'N/A'} | Conns: ${pt.conns} | RT: ${pt.rt !== null ? pt.rt + 'ms' : '-'}`"
        ></div>
      </div>

      <!-- Sparklines: Response Time & Active Connections -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div class="bg-[#060a14] border border-gray-800/80 rounded p-2.5">
          <div class="text-[10px] text-gray-400 uppercase font-bold mb-1">Response Time (ms)</div>
          <svg viewBox="0 0 300 48" class="w-full h-12 overflow-visible">
            <polyline v-if="rtPolyline" :points="rtPolyline" fill="none" stroke="#38bdf8" stroke-width="1.8" stroke-linejoin="round" />
          </svg>
        </div>
        <div class="bg-[#060a14] border border-gray-800/80 rounded p-2.5">
          <div class="text-[10px] text-gray-400 uppercase font-bold mb-1">Active Connections</div>
          <svg viewBox="0 0 300 48" class="w-full h-12 overflow-visible">
            <polyline v-if="connPolyline" :points="connPolyline" fill="none" stroke="#34d399" stroke-width="1.8" stroke-linejoin="round" />
          </svg>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'

const props = defineProps({
  serverId: { type: [Number, String], required: true },
  serviceId: { type: [Number, String], required: true },
  serviceName: { type: String, default: '' },
})

defineEmits(['close'])

const ranges = [
  { id: 'today', label: 'Today' },
  { id: '1h', label: '1h' },
  { id: '24h', label: '24h' },
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
]

const selectedRange = ref('24h')
const loading = ref(false)
const points = ref([])
const nowStatus = ref('unknown')
const nowConns = ref(0)
const nowRt = ref(null)

async function fetchHistory() {
  if (!props.serverId || !props.serviceId) return
  loading.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/services/${props.serviceId}/history?range=${selectedRange.value}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (data.ok) {
      points.value = data.points || []
      nowStatus.value = data.now?.status || 'unknown'
      nowConns.value = data.now?.connections ?? 0
      nowRt.value = data.now?.response_time_ms ?? null
    }
  } catch (err) {
    console.error('Failed to load service history:', err)
  } finally {
    loading.value = false
  }
}

watch([() => props.serviceId, selectedRange], fetchHistory)
onMounted(fetchHistory)

const uptimePct = computed(() => {
  const valid = points.value.filter(p => p.up_ratio !== null)
  if (!valid.length) return null
  const avg = valid.reduce((acc, p) => acc + p.up_ratio, 0) / valid.length
  return Math.round(avg * 1000) / 10
})

const uptimeBadgeClass = computed(() => {
  if (uptimePct.value === null) return 'bg-gray-800 text-gray-400'
  if (uptimePct.value >= 99) return 'bg-emerald-950 text-emerald-300 border border-emerald-700/60'
  if (uptimePct.value >= 95) return 'bg-amber-950 text-amber-300 border border-amber-700/60'
  return 'bg-rose-950 text-rose-300 border border-rose-700/60'
})

function stripColor(pt) {
  if (pt.up_ratio === null) return 'bg-gray-700'
  if (pt.up_ratio >= 0.99) return 'bg-emerald-500'
  if (pt.up_ratio >= 0.5) return 'bg-amber-500'
  return 'bg-rose-500'
}

function buildPolyline(values) {
  if (values.length < 2) return ''
  const max = Math.max(...values, 1)
  return values.map((v, i) => {
    const x = (i / (values.length - 1)) * 300
    const y = 44 - (v / max) * 40
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

const rtPolyline = computed(() => buildPolyline(points.value.map(p => p.rt ?? 0)))
const connPolyline = computed(() => buildPolyline(points.value.map(p => p.conns ?? 0)))

function formatTs(epochSec) {
  return new Date(epochSec * 1000).toLocaleString()
}
</script>
