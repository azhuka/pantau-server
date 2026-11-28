<template>
  <div v-if="probe" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4" @keydown.esc="$emit('close')">
    <div class="hud-tactical-card rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200 font-mono overflow-hidden">
      <div class="flex items-center justify-between border-b border-gray-800 px-5 py-3.5 shrink-0">
        <div>
          <h3 class="text-sm font-bold text-cyan-300 uppercase tracking-wider">Endpoint Check History — {{ probe.name }}</h3>
          <p class="text-[11px] text-gray-400 mt-0.5">{{ probe.probe_type.toUpperCase() }} · {{ probe.target }}{{ probe.port ? `:${probe.port}` : '' }}</p>
        </div>
        <button type="button" @click="$emit('close')" class="text-gray-400 hover:text-white cursor-pointer p-1" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <div class="p-5 space-y-4 overflow-y-auto flex-1 text-xs">
        <div v-if="loading" class="text-center py-8 text-cyan-400">Loading probe execution history...</div>
        <template v-else>
          <!-- Latency Bar Strip -->
          <div class="p-3 rounded-lg bg-[#070c18] border border-gray-800">
            <div class="flex items-center justify-between text-[11px] text-gray-400 mb-2">
              <span>Recent Latency Trend ({{ logs.length }} checks)</span>
              <span>24h Uptime: <strong class="text-emerald-400">{{ probe.uptime_24h ?? 100 }}%</strong></span>
            </div>
            <div v-if="orderedLogs.length" class="flex items-end gap-1 h-16 pt-2">
              <div
                v-for="l in orderedLogs"
                :key="l.id"
                class="flex-1 min-w-[3px] rounded-t transition-all"
                :class="l.status === 'up' ? 'bg-emerald-500/80' : (l.status === 'degraded' ? 'bg-amber-500/80' : 'bg-rose-500/80')"
                :style="{ height: barHeight(l) }"
                :title="`${formatTime(l.checked_at)} | ${l.status.toUpperCase()} | ${l.latency_ms ?? '-'} ms${l.error_message ? ' | ' + l.error_message : ''}`"
              ></div>
            </div>
            <div v-else class="text-gray-500 text-center py-4">No check history recorded yet.</div>
          </div>

          <!-- Log Table -->
          <div class="overflow-x-auto border border-gray-800 rounded-lg">
            <table class="w-full text-left border-collapse">
              <thead>
                <tr class="bg-[#070c18] border-b border-gray-800 text-gray-400 font-bold">
                  <th class="py-2 px-3">{{ t('th_checked_at') }}</th>
                  <th class="py-2 px-3">{{ t('th_status') }}</th>
                  <th class="py-2 px-3 text-right">{{ t('th_latency') }}</th>
                  <th class="py-2 px-3">{{ t('th_http_details') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-800/50">
                <tr v-for="l in logs" :key="l.id" class="hover:bg-cyan-950/15">
                  <td class="py-1.5 px-3 text-gray-400 whitespace-nowrap">{{ formatTime(l.checked_at) }}</td>
                  <td class="py-1.5 px-3 whitespace-nowrap">
                    <span
                      class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                      :class="l.status === 'up' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60' : (l.status === 'degraded' ? 'bg-amber-950/80 text-amber-300 border border-amber-700/60' : 'bg-rose-950/80 text-rose-300 border border-rose-700/60')"
                    >
                      {{ l.status }}
                    </span>
                  </td>
                  <td class="py-1.5 px-3 text-right text-gray-200 whitespace-nowrap">{{ l.latency_ms !== null ? `${Math.round(l.latency_ms)} ms` : '—' }}</td>
                  <td class="py-1.5 px-3 text-gray-300">
                    <span v-if="l.status_code" class="text-cyan-300 mr-2">HTTP {{ l.status_code }}</span>
                    <span class="text-rose-300">{{ l.error_message || (l.status === 'up' ? 'OK' : '') }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>

      <div class="flex justify-end px-5 py-3 border-t border-gray-800 bg-[#070c18]/80 shrink-0 text-xs">
        <button type="button" @click="$emit('close')" class="px-4 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold cursor-pointer">Close</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import { apiFetch } from '../../../utils/api'

const props = defineProps({ probe: { type: Object, default: null } })
defineEmits(['close'])
const { t } = useI18n()

const loading = ref(false)
const logs = ref([])

const orderedLogs = computed(() => [...logs.value].reverse())
const maxLatency = computed(() => Math.max(100, ...logs.value.map(l => Number(l.latency_ms || 0))))

function barHeight(l) {
  if (l.status === 'down') return '100%'
  const pct = Math.max(15, Math.min(100, Math.round((Number(l.latency_ms || 10) / maxLatency.value) * 100)))
  return `${pct}%`
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

watch(() => props.probe, async (p) => {
  if (!p) return
  loading.value = true
  try {
    const res = await apiFetch(`/api/probes/${p.id}/history?limit=60`)
    const data = await res.json()
    logs.value = data.logs || []
  } catch {
    logs.value = []
  } finally {
    loading.value = false
  }
}, { immediate: true })
</script>
