<template>
  <div
    v-if="isOpen && probe"
    class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono text-xs"
    @click.self="$emit('close')"
  >
    <div class="bg-[#0b1220] border border-cyan-500/40 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
      <div class="px-5 py-3 border-b border-gray-800 bg-[#070c18] flex items-center justify-between shrink-0">
        <div>
          <h3 class="text-sm font-bold text-cyan-300">Probe History: {{ probe.name }}</h3>
          <p class="text-[11px] text-gray-400">{{ probe.probe_type?.toUpperCase() }} · {{ probe.target }}</p>
        </div>
        <button type="button" @click="$emit('close')" class="p-1 text-gray-400 hover:text-white cursor-pointer" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Latency Sparkline SVG -->
      <div v-if="latencyPoints.length > 1" class="px-5 py-3 border-b border-gray-800 bg-[#080e1a] shrink-0">
        <div class="flex items-center justify-between text-[11px] text-gray-400 mb-1.5">
          <span>Latency Trend (ms)</span>
          <span>Avg: {{ avgLatency }} ms · Max: {{ maxLatency }} ms</span>
        </div>
        <svg viewBox="0 0 600 70" class="w-full h-16 overflow-visible">
          <polyline
            fill="none"
            stroke="#22d3ee"
            stroke-width="2"
            :points="svgPolyline"
          />
        </svg>
      </div>

      <div class="flex-1 overflow-y-auto">
        <div v-if="loading" class="py-10 text-center text-gray-400">Loading probe execution history...</div>
        <table v-else class="w-full text-left border-collapse">
          <thead class="sticky top-0 bg-[#0b1220] text-[10px] uppercase text-gray-400 border-b border-gray-800">
            <tr>
              <th class="px-3 py-2">{{ t('th_time') }}</th>
              <th class="px-3 py-2">{{ t('th_status') }}</th>
              <th class="px-3 py-2">{{ t('th_latency') }}</th>
              <th class="px-3 py-2">{{ t('th_status_code') }}</th>
              <th class="px-3 py-2">{{ t('th_details') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr v-if="logs.length === 0">
              <td colspan="5" class="px-4 py-8 text-center text-gray-500">No probe history recorded yet.</td>
            </tr>
            <tr v-for="l in paginatedLogs" :key="l.id" class="hover:bg-cyan-950/15">
              <td class="px-3 py-1.5 text-gray-400 whitespace-nowrap">{{ formatIncidentTime(l.checked_at) }}</td>
              <td class="px-3 py-1.5">
                <span :class="l.status === 'up' ? 'text-emerald-400' : l.status === 'degraded' ? 'text-amber-400' : 'text-rose-400'" class="font-bold uppercase">
                  {{ l.status }}
                </span>
              </td>
              <td class="px-3 py-1.5 text-cyan-300">{{ l.latency_ms != null ? `${Math.round(l.latency_ms)} ms` : '-' }}</td>
              <td class="px-3 py-1.5 text-gray-300">{{ l.status_code || '-' }}</td>
              <td class="px-3 py-1.5 text-gray-400 break-all">{{ l.error_message || 'OK' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="px-4 py-2 border-t border-gray-800 bg-[#070c18]">
        <NocTablePagination v-model:page="page" v-model:pageSize="pageSize" :total="logs.length" unitLabel="checks" :pageSizeOptions="[10, 25, 50]" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '../../i18n'
import { apiFetch } from '../../utils/api'
import { formatIncidentTime } from '../../utils/formatters'
import NocTablePagination from '../common/NocTablePagination.vue'

const { t } = useI18n()
const props = defineProps({
  isOpen: Boolean,
  probe: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const logs = ref([])
const page = ref(1)
const pageSize = ref(10)

const paginatedLogs = computed(() => logs.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const latencyPoints = computed(() => [...logs.value].reverse().map((l) => l.latency_ms).filter((v) => v != null))
const maxLatency = computed(() => (latencyPoints.value.length ? Math.round(Math.max(...latencyPoints.value)) : 0))
const avgLatency = computed(() => (latencyPoints.value.length ? Math.round(latencyPoints.value.reduce((a, b) => a + b, 0) / latencyPoints.value.length) : 0))

const svgPolyline = computed(() => {
  const pts = latencyPoints.value
  if (pts.length < 2) return ''
  const max = Math.max(...pts, 10)
  return pts.map((v, i) => `${(i / (pts.length - 1)) * 600},${65 - (v / max) * 58}`).join(' ')
})

async function loadHistory() {
  if (!props.probe?.id) return
  loading.value = true
  try {
    const res = await apiFetch(`/api/probes/${props.probe.id}/history?limit=100`)
    if (res.ok) {
      const data = await res.json()
      logs.value = data.logs || []
    }
  } finally {
    loading.value = false
  }
}

function onEsc(e) {
  if (props.isOpen && e.key === 'Escape') emit('close')
}

watch(() => props.isOpen, (open) => {
  if (open) {
    page.value = 1
    loadHistory()
    window.addEventListener('keydown', onEsc)
  } else {
    window.removeEventListener('keydown', onEsc)
  }
})

onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>
