<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>

    <div class="flex items-center justify-between flex-wrap gap-2 border-b border-cyan-500/20 pb-2">
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">Performance Metric History</h3>
      <div class="flex items-center gap-1">
        <button
          v-for="r in RANGES"
          :key="r.id"
          type="button"
          @click="selectedRange = r.id"
          class="px-2 py-0.5 rounded text-[11px] font-bold border transition cursor-pointer"
          :class="selectedRange === r.id
            ? 'bg-cyan-950 text-cyan-300 border-cyan-500/60'
            : 'bg-gray-900/60 text-gray-400 border-gray-800 hover:text-gray-200'"
        >
          {{ r.label }}
        </button>
      </div>
    </div>

    <div v-if="loading && points.length === 0" class="text-xs text-gray-400 py-8 text-center">
      Loading telemetry history...
    </div>
    <div v-else-if="points.length < 2" class="text-xs text-gray-500 py-8 text-center">
      Not enough telemetry snapshots collected for this time range yet.
    </div>
    <div v-else class="space-y-3" :class="loading ? 'opacity-65 transition-opacity' : ''">
      <!-- 2x2 Symmetrical Grid: CPU, Memory, Disk, Load Average -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div
          v-for="cfg in CHARTS"
          :key="cfg.key"
          class="bg-[#050811] border border-cyan-900/40 rounded-lg p-3 relative select-none"
        >
          <div class="flex items-center justify-between mb-1.5 text-[11px]">
            <span class="font-bold text-gray-300">{{ cfg.title }}</span>
            <span class="font-bold" :style="{ color: cfg.color }">
              {{ hoveredIdx !== null && points[hoveredIdx]?.[cfg.key] != null
                ? formatVal(points[hoveredIdx][cfg.key], cfg.unit)
                : formatVal(latestVal(cfg.key), cfg.unit) }}
            </span>
          </div>
          <svg
            viewBox="0 0 360 88"
            class="w-full h-[88px] overflow-visible cursor-crosshair"
            @mousemove="onHover($event)"
            @mouseleave="hoveredIdx = null"
          >
            <defs>
              <linearGradient :id="`grad-${cfg.key}`" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" :stop-color="cfg.color" stop-opacity="0.32" />
                <stop offset="100%" :stop-color="cfg.color" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <line x1="0" y1="22" x2="360" y2="22" stroke="rgba(148,163,184,0.1)" stroke-dasharray="3 3" />
            <line x1="0" y1="44" x2="360" y2="44" stroke="rgba(148,163,184,0.1)" stroke-dasharray="3 3" />
            <line x1="0" y1="66" x2="360" y2="66" stroke="rgba(148,163,184,0.1)" stroke-dasharray="3 3" />
            <path :d="buildAreaPath(cfg.key, cfg.fixedMax)" :fill="`url(#grad-${cfg.key})`" />
            <path :d="buildLinePath(cfg.key, cfg.fixedMax)" fill="none" :stroke="cfg.color" stroke-width="1.8" />
            <line
              v-if="hoveredIdx !== null"
              :x1="xAt(hoveredIdx)"
              y1="0"
              :x2="xAt(hoveredIdx)"
              y2="84"
              stroke="rgba(226,232,240,0.45)"
              stroke-dasharray="2 2"
            />
            <circle
              v-if="hoveredIdx !== null && points[hoveredIdx]?.[cfg.key] != null"
              :cx="xAt(hoveredIdx)"
              :cy="yAt(points[hoveredIdx][cfg.key], cfg.key, cfg.fixedMax)"
              r="3.2"
              :fill="cfg.color"
              stroke="#050811"
              stroke-width="1.5"
            />
          </svg>
          <div class="flex justify-between text-[10px] text-gray-500 mt-1">
            <span>{{ fmtTime(points[0]?.t) }}</span>
            <span v-if="hoveredIdx !== null" class="text-cyan-300">{{ fmtTime(points[hoveredIdx]?.t) }}</span>
            <span>{{ fmtTime(points[points.length - 1]?.t) }}</span>
          </div>
        </div>
      </div>

      <!-- Standalone Network Throughput Card -->
      <div class="bg-[#050811] border border-cyan-900/40 rounded-lg p-3 relative select-none">
        <div class="flex items-center justify-between mb-1.5 text-[11px] flex-wrap gap-2">
          <span class="font-bold text-gray-300">Network Throughput (RX / TX)</span>
          <div class="flex items-center gap-3 text-[11px]">
            <span class="text-cyan-300 font-bold">
              RX: {{ formatBps(hoveredIdx !== null ? points[hoveredIdx]?.net_rx : latestVal('net_rx')) }}
            </span>
            <span class="text-emerald-400 font-bold">
              TX: {{ formatBps(hoveredIdx !== null ? points[hoveredIdx]?.net_tx : latestVal('net_tx')) }}
            </span>
          </div>
        </div>
        <svg
          viewBox="0 0 720 76"
          class="w-full h-[76px] overflow-visible cursor-crosshair"
          @mousemove="onHover($event, 720)"
          @mouseleave="hoveredIdx = null"
        >
          <line x1="0" y1="38" x2="720" y2="38" stroke="rgba(148,163,184,0.1)" stroke-dasharray="3 3" />
          <path :d="buildLinePath('net_rx', null, 720, 72)" fill="none" stroke="#38bdf8" stroke-width="1.6" />
          <path :d="buildLinePath('net_tx', null, 720, 72)" fill="none" stroke="#10b981" stroke-width="1.6" />
          <line
            v-if="hoveredIdx !== null"
            :x1="xAt(hoveredIdx, 720)"
            y1="0"
            :x2="xAt(hoveredIdx, 720)"
            y2="72"
            stroke="rgba(226,232,240,0.45)"
            stroke-dasharray="2 2"
          />
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  serverId: { type: [Number, String], default: null },
})

const RANGES = [
  { id: '1h', label: '1h' },
  { id: '6h', label: '6h' },
  { id: '24h', label: '24h' },
  { id: 'today', label: 'Today' },
  { id: '7d', label: '7d' },
  { id: '30d', label: '30d' },
]

const CHARTS = [
  { key: 'cpu', title: 'CPU Usage (%)', unit: '%', color: '#38bdf8', fixedMax: 100 },
  { key: 'mem_pct', title: 'Memory Usage (%)', unit: '%', color: '#10b981', fixedMax: 100 },
  { key: 'disk', title: 'Disk Usage (%)', unit: '%', color: '#f59e0b', fixedMax: 100 },
  { key: 'load1', title: 'Load Average (1m)', unit: '', color: '#a855f7', fixedMax: null },
]

const selectedRange = ref('24h')
const points = ref([])
const loading = ref(false)
const hoveredIdx = ref(null)
let abortCtrl = null

async function fetchPerf() {
  if (!props.serverId) return
  if (abortCtrl) abortCtrl.abort()
  abortCtrl = new AbortController()
  loading.value = true
  try {
    const token = localStorage.getItem('pantau_token') || ''
    const res = await fetch(`/api/servers/${props.serverId}/perf?range=${selectedRange.value}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: abortCtrl.signal,
    })
    if (res.ok) {
      const data = await res.json()
      points.value = data.points || []
    }
  } catch (err) {
    if (err.name !== 'AbortError') points.value = []
  } finally {
    loading.value = false
  }
}

watch(() => [props.serverId, selectedRange.value], () => {
  hoveredIdx.value = null
  fetchPerf()
}, { immediate: true })

function latestVal(key) {
  for (let i = points.value.length - 1; i >= 0; i--) {
    if (points.value[i]?.[key] != null) return points.value[i][key]
  }
  return null
}

function maxFor(key, fixedMax) {
  if (fixedMax) return fixedMax
  let max = 0
  for (const p of points.value) {
    const v = Number(p?.[key] ?? 0)
    if (v > max) max = v
  }
  return Math.max(max * 1.15, 1)
}

function xAt(idx, width = 360) {
  const n = points.value.length
  if (n <= 1) return 0
  return (idx / (n - 1)) * width
}

function yAt(val, key, fixedMax, height = 84) {
  const m = maxFor(key, fixedMax)
  const clamped = Math.max(0, Math.min(Number(val ?? 0), m))
  return height - (clamped / m) * (height - 6) - 3
}

function buildLinePath(key, fixedMax, width = 360, height = 84) {
  let d = ''
  points.value.forEach((p, idx) => {
    if (p?.[key] == null) return
    const cmd = d ? 'L' : 'M'
    d += `${cmd}${xAt(idx, width).toFixed(1)},${yAt(p[key], key, fixedMax, height).toFixed(1)} `
  })
  return d.trim()
}

function buildAreaPath(key, fixedMax, width = 360, height = 84) {
  const line = buildLinePath(key, fixedMax, width, height)
  if (!line) return ''
  return `${line} L${width},${height} L0,${height} Z`
}

function onHover(ev, width = 360) {
  const rect = ev.currentTarget.getBoundingClientRect()
  if (!rect.width || points.value.length < 2) return
  const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
  hoveredIdx.value = Math.round(ratio * (points.value.length - 1))
}

function formatVal(v, unit) {
  if (v == null) return '-'
  return unit === '%' ? `${Number(v).toFixed(1)}%` : Number(v).toFixed(2)
}

function formatBps(bps) {
  if (bps == null) return '-'
  const v = Number(bps)
  if (v < 1024) return `${v.toFixed(0)} B/s`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB/s`
  return `${(v / (1024 * 1024)).toFixed(2)} MB/s`
}

function fmtTime(epochSec) {
  if (!epochSec) return ''
  const d = new Date(epochSec * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>
