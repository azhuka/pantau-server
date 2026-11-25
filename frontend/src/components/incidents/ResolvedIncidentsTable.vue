<template>
  <div class="space-y-3">
    <!-- Resolved / MTTR History Card -->
    <div class="hud-tactical-card rounded-xl border border-gray-800 bg-[#0a0f1d] shadow-lg p-4 font-mono select-none">
      <!-- Header & MTTR KPI Ribbon -->
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-gray-800/80">
        <div>
          <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider flex items-center gap-2">
            <span>{{ t('inc_resolved_title') }}</span>
            <span class="text-xs px-2 py-0.5 rounded-full font-extrabold bg-blue-500/20 text-blue-300 border border-blue-500/30">
              {{ stats.total || problems.length }}
            </span>
          </h3>
          <p class="text-[11px] text-gray-400 mt-0.5">{{ t('inc_resolved_subtitle') }}</p>
        </div>

        <!-- MTTR Summary Badges -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div class="bg-[#060a14] px-2.5 py-1.5 rounded border border-gray-800">
            <div class="text-[10px] text-gray-500 uppercase">{{ t('inc_stat_avg_mttr') }}</div>
            <div class="font-extrabold text-cyan-300 text-sm">{{ stats.avg_mttr_formatted || '-' }}</div>
          </div>
          <div class="bg-[#060a14] px-2.5 py-1.5 rounded border border-gray-800">
            <div class="text-[10px] text-gray-500 uppercase">{{ t('inc_stat_total_resolved') }}</div>
            <div class="font-extrabold text-gray-200 text-sm">{{ stats.total || 0 }}</div>
          </div>
          <div class="bg-[#060a14] px-2.5 py-1.5 rounded border border-gray-800">
            <div class="text-[10px] text-gray-500 uppercase">{{ t('inc_stat_auto_healed') }}</div>
            <div class="font-extrabold text-emerald-400 text-sm">{{ stats.auto_count || 0 }}</div>
          </div>
          <div class="bg-[#060a14] px-2.5 py-1.5 rounded border border-gray-800">
            <div class="text-[10px] text-gray-500 uppercase">{{ t('inc_stat_manual') }}</div>
            <div class="font-extrabold text-cyan-400 text-sm">{{ stats.manual_count || 0 }}</div>
          </div>
        </div>
      </div>

      <!-- Filters & Search Toolbar -->
      <ResolvedIncidentsFilterBar
        :servers="servers"
        :period="period" :start-date="startDate" :end-date="endDate"
        @update:period="$emit('update:period', $event)"
        @update:start-date="$emit('update:startDate', $event)"
        @update:end-date="$emit('update:endDate', $event)"
        v-model:serverId="selectedServerId" v-model:severity="severityFilter" v-model:resType="typeFilter" v-model:search="searchQuery"
        :filtered-count="filteredProblems.length" :total-count="problems.length"
        @reset="resetFilters"
      />

      <!-- Table Content -->
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('inc_col_resolved_at') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_asset') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_sev') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_event') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_mttr') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_res_type') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('inc_col_tindakan') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-if="paginatedProblems.length === 0">
              <td colspan="7" class="py-8 text-center text-gray-500 italic">
                {{ t('inc_empty_resolved') }}
              </td>
            </tr>
            <tr
              v-for="prob in paginatedProblems"
              :key="prob.id"
              class="hover:bg-cyan-950/20 transition-colors group"
            >
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap" :title="prob.resolved_at">
                {{ formatIncidentTime(prob.resolved_at) }}
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="font-bold text-gray-300">{{ prob.hostname || `Server #${prob.server_id}` }}</span>
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border" :class="severityBadgeClass(prob.severity)">
                  {{ prob.severity }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-300">
                <span class="font-medium">{{ formatIncidentMessage(prob, locale) }}</span>
              </td>
              <td class="py-2.5 px-3 text-cyan-300 font-bold whitespace-nowrap">
                {{ formatMttr(prob) }}
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border"
                  :class="resBadgeClass(prob)"
                  :title="prob.resolved_note || ''"
                >
                  {{ resModeLabel(prob) }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <div class="inline-flex items-center justify-end">
                  <button
                    @click="$emit('open-workspace', { server_id: prob.server_id, problem: prob })"
                    class="w-[26px] h-[26px] min-w-[26px] p-0 flex items-center justify-center rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700/80 transition cursor-pointer"
                    :title="t('inc_btn_workspace')"
                    :aria-label="t('inc_btn_workspace')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredProblems.length" unitLabel="incidents" :pageSizeOptions="[10, 25, 50, 100, 'all']" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentTime, formatIncidentMessage } from '../../utils/formatters'
import { inferResolutionType, RESOLUTION_TYPE_LABELS } from '../../utils/filterHelpers'
import NocTablePagination from '../common/NocTablePagination.vue'
import ResolvedIncidentsFilterBar from './ResolvedIncidentsFilterBar.vue'

const { t, locale } = useI18n()

const props = defineProps({
  problems: { type: Array, default: () => [] },
  servers: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({}) },
  period: { type: String, default: '24h' },
  startDate: { type: String, default: '' },
  endDate: { type: String, default: '' },
})

const emit = defineEmits(['update:period', 'update:startDate', 'update:endDate', 'open-workspace'])

const selectedServerId = ref('')
const severityFilter = ref('')
const typeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

watch([selectedServerId, severityFilter, typeFilter, searchQuery], () => {
  currentPage.value = 1
})

function resetFilters() {
  selectedServerId.value = ''
  severityFilter.value = ''
  typeFilter.value = 'all'
  searchQuery.value = ''
  emit('update:startDate', '')
  emit('update:endDate', '')
  emit('update:period', '24h')
}

function resModeLabel(prob) {
  const mode = inferResolutionType(prob)
  return RESOLUTION_TYPE_LABELS[mode] || mode
}

function resBadgeClass(prob) {
  const mode = inferResolutionType(prob)
  if (mode === 'manual') return 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30'
  if (mode === 'stale_closed') return 'bg-gray-700/40 text-gray-300 border-gray-600'
  return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
}

function formatMttr(prob) {
  if (prob.duration_sec !== undefined && prob.duration_sec !== null) {
    const s = Math.round(prob.duration_sec)
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60)
    const remS = s % 60
    if (m < 60) return remS > 0 ? `${m}m ${remS}s` : `${m}m`
    const h = Math.floor(m / 60)
    return `${h}h ${m % 60}m`
  }
  const startTime = prob.started_at || prob.created_at
  if (startTime && prob.resolved_at) {
    try {
      const start = new Date(startTime).getTime()
      const end = new Date(prob.resolved_at).getTime()
      const diffSec = Math.max(0, Math.floor((end - start) / 1000))
      const m = Math.floor(diffSec / 60)
      if (m < 60) return `${m}m`
      return `${Math.floor(m / 60)}h ${m % 60}m`
    } catch {
      return '-'
    }
  }
  return '-'
}

function severityBadgeClass(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'danger') return 'bg-red-500/20 text-red-400 border-red-500/30'
  if (s === 'critical') return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
  if (s === 'warning') return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
  return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
}

const filteredProblems = computed(() => {
  return props.problems.filter(p => {
    if (selectedServerId.value && String(p.server_id) !== selectedServerId.value) return false
    if (severityFilter.value) {
      const sev = (p.severity || '').toLowerCase()
      if (severityFilter.value === 'critical') {
        if (sev !== 'critical' && sev !== 'average') return false
      } else if (sev !== severityFilter.value) {
        return false
      }
    }
    if (typeFilter.value !== 'all' && inferResolutionType(p) !== typeFilter.value) return false

    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      const hay = `${p.hostname || ''} ${p.group_name || ''} ${p.message || ''} ${p.component || ''} ${p.resolved_note || ''} ${p.key || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const paginatedProblems = computed(() => {
  if (pageSize.value === 'all') return filteredProblems.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredProblems.value.slice(start, start + limit)
})
</script>