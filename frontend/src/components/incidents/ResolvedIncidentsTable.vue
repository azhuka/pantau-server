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
      <div class="flex flex-wrap items-center justify-between gap-2 py-2 text-xs">
        <div class="flex flex-wrap items-center gap-2">
          <!-- Period Selector -->
          <div class="flex items-center gap-1.5">
            <span class="text-gray-400 text-[11px]">{{ t('audit_period') }}</span>
            <select
              :value="period"
              @change="$emit('update:period', $event.target.value)"
              class="bg-[#060a14] border border-gray-800 text-gray-200 rounded px-2 py-1 text-xs focus:border-cyan-500 focus:outline-none cursor-pointer"
            >
              <option value="today">{{ t('inc_period_today') }}</option>
              <option value="24h">{{ t('inc_period_24h') }}</option>
              <option value="7d">{{ t('inc_period_7d') }}</option>
              <option value="30d">{{ t('inc_period_30d') }}</option>
              <option value="all">{{ t('inc_period_all') }}</option>
            </select>
          </div>

          <!-- Type Filter -->
          <div class="flex items-center gap-1.5">
            <select
              v-model="typeFilter"
              class="bg-[#060a14] border border-gray-800 text-gray-200 rounded px-2 py-1 text-xs focus:border-cyan-500 focus:outline-none cursor-pointer"
            >
              <option value="all">{{ t('inc_type_all') }}</option>
              <option value="auto">{{ t('inc_type_auto') }}</option>
              <option value="manual">{{ t('inc_type_manual') }}</option>
            </select>
          </div>
        </div>

        <input
          v-model="searchQuery"
          type="text"
          :placeholder="t('inc_search_placeholder')"
          class="bg-[#060a14] border border-gray-800 focus:border-cyan-500 rounded px-2.5 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none w-48"
        />
      </div>

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
                  :class="isAutoHealed(prob) ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30'"
                >
                  {{ isAutoHealed(prob) ? t('inc_res_mode_auto') : t('inc_res_mode_manual') }}
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

      <!-- Pagination bar: strictly hidden if filtered count <= 10 -->
      <div v-if="filteredProblems.length > 10" class="flex items-center justify-between pt-3 border-t border-gray-800 text-xs text-gray-400 mt-2">
        <span>Page {{ currentPage }} of {{ totalPages }} ({{ filteredProblems.length }} total)</span>
        <div class="flex items-center gap-1">
          <button :disabled="currentPage <= 1" @click="currentPage--" class="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-30 cursor-pointer">Prev</button>
          <button :disabled="currentPage >= totalPages" @click="currentPage++" class="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-30 cursor-pointer">Next</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentTime, formatIncidentMessage } from '../../utils/formatters'

const { t, locale } = useI18n()

const props = defineProps({
  problems: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({}) },
  period: { type: String, default: '24h' }
})

defineEmits(['update:period', 'open-workspace'])

const typeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 10

function isAutoHealed(prob) {
  if (prob.acknowledged_by) return false
  const note = (prob.resolved_note || '').toLowerCase()
  return note.includes('auto-healed') || note.includes('automatic') || !note
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
    if (typeFilter.value === 'auto' && !isAutoHealed(p)) return false
    if (typeFilter.value === 'manual' && isAutoHealed(p)) return false

    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      const matchHost = (p.hostname || '').toLowerCase().includes(q)
      const matchMsg = (p.message || '').toLowerCase().includes(q)
      if (!matchHost && !matchMsg) return false
    }
    return true
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredProblems.value.length / pageSize)))

const paginatedProblems = computed(() => {
  if (filteredProblems.value.length <= pageSize) return filteredProblems.value
  const start = (currentPage.value - 1) * pageSize
  return filteredProblems.value.slice(start, start + pageSize)
})
</script>