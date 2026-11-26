<template>
  <div class="space-y-3">
    <!-- Active Table Card -->
    <div class="hud-tactical-card rounded-xl border border-gray-800 bg-[#0a0f1d] shadow-lg p-4 font-mono select-none">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-gray-800/80">
        <!-- Title & Live Counter -->
        <div class="flex items-center gap-2.5">
          <span class="w-2.5 h-2.5 rounded-full" :class="filteredProblems.length > 0 ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'"></span>
          <div>
            <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider flex items-center gap-2">
              <span>{{ t('inc_active_title') }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full font-extrabold" :class="filteredProblems.length > 0 ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'">
                {{ filteredProblems.length }}
              </span>
            </h3>
            <p class="text-[11px] text-gray-400 mt-0.5">{{ t('inc_active_subtitle') }}</p>
          </div>
        </div>
      </div>

      <!-- Unified Blueprint Filter Bar & Triage Pills -->
      <ActiveIncidentsFilterBar
        :servers="servers"
        :pill-counts="pillCounts"
        v-model:serverId="selectedServerId"
        v-model:group="selectedGroup"
        v-model:severity="activeFilter"
        v-model:search="searchQuery"
        :filtered-count="filteredProblems.length"
        :total-count="problems.length"
        @reset="resetFilters"
      />

      <!-- Table Content (Canonical 7 Columns) -->
      <div class="overflow-x-auto mt-2">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('inc_col_start') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_asset') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_sev') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_event') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_durasi') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_solution') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('inc_col_tindakan') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-if="paginatedProblems.length === 0">
              <td colspan="7" class="py-8 text-center text-gray-500 italic">
                {{ problems.length === 0 ? t('inc_empty_active') : t('inc_empty_filtered') }}
              </td>
            </tr>
            <tr v-for="prob in paginatedProblems" :key="prob.id" class="hover:bg-cyan-950/20 transition-colors group">
              <!-- 1. Start Time -->
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap" :title="prob.started_at || prob.created_at">
                {{ formatIncidentTime(prob.started_at || prob.created_at) }}
              </td>
              <!-- 2. Asset Host -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="font-bold text-cyan-300">{{ prob.hostname || `Server #${prob.server_id}` }}</span>
              </td>
              <!-- 3. Severity & Status Badge -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="inline-flex flex-col items-start gap-1">
                  <span class="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase border" :class="severityBadgeClass(prob.severity)">
                    {{ prob.severity }}
                  </span>
                  <span
                    v-if="prob.acknowledged_by"
                    class="text-[9px] px-1.5 py-0.2 rounded font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-0.5 shadow-sm"
                    :title="t('dash_acked_by', { user: prob.acknowledged_by })"
                  >
                    <svg class="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><span>{{ t('dash_badge_handled') }}</span>
                  </span>
                  <span
                    v-if="prob.is_ignored"
                    class="text-[9px] px-1.5 py-0.2 rounded font-bold bg-gray-700/50 text-gray-300 border border-gray-600 flex items-center gap-0.5"
                    :title="prob.ignored_reason || t('inc_filter_ignored')"
                  >
                    <span>{{ t('inc_filter_ignored') }}</span>
                  </span>
                </div>
              </td>
              <!-- 4. Incident Description -->
              <td class="py-2.5 px-3 text-gray-200">
                <span class="font-medium">{{ formatIncidentMessage(prob, locale) }}</span>
              </td>
              <!-- 5. Duration -->
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap">
                {{ formatIncidentDuration(prob.started_at || prob.created_at, locale) }}
              </td>
              <!-- 6. Solution -->
              <td class="py-2.5 px-3 text-gray-400">
                <span class="font-mono text-[11px] truncate max-w-xs block cursor-help" :title="formatIncidentTip(prob, locale) || '—'">
                  {{ formatIncidentTip(prob, locale) || '—' }}
                </span>
              </td>
              <!-- 7. Actions -->
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <!-- Viewer: Single View Icon -->
                <button
                  v-if="!canOperate"
                  @click="$emit('open-workspace', { server_id: prob.server_id, problem: prob })"
                  class="w-[26px] h-[26px] min-w-[26px] p-0 flex items-center justify-center rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700/80 transition cursor-pointer"
                  :title="t('inc_btn_workspace')"
                  :aria-label="t('inc_btn_workspace')"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>

                <!-- Operator / Admin: Floating Teleported Action Dropdown -->
                <button
                  v-else
                  type="button"
                  @click.stop="toggleActDropdown(prob, $event)"
                  class="h-6 min-w-[58px] px-2 py-0.5 rounded bg-[#0b1324] hover:bg-cyan-950/60 text-cyan-300 border border-gray-700 hover:border-cyan-500 font-bold text-[11px] transition cursor-pointer inline-flex items-center justify-between gap-1 select-none"
                >
                  <span>{{ t('inc_act_dropdown') }}</span>
                  <svg class="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredProblems.length" unitLabel="incidents" :pageSizeOptions="[10, 25, 50, 100, 'all']" />

      <Teleport to="body">
        <div
          v-if="openActId && activeActProb"
          @click.stop
          :style="actDropdownStyle"
          class="rounded-md bg-[#0a0f1d] border border-gray-700 shadow-2xl py-1 z-[100005] text-xs font-mono"
        >
          <button @click="$emit('open-workspace', { server_id: activeActProb.server_id, problem: activeActProb }); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <span>{{ t('inc_btn_workspace') }}</span>
          </button>
          <div v-if="activeActProb.acknowledged_by" class="w-full text-left px-3 py-1.5 text-emerald-400 font-bold flex items-center gap-2 cursor-default select-none border-t border-gray-800/60" :title="t('dash_acked_by', { user: activeActProb.acknowledged_by })">
            <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>{{ t('inc_btn_ack_done') }}</span>
          </div>
          <button v-else @click="$emit('ack', activeActProb.id); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60">
            <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>{{ t('inc_btn_ack') }}</span>
          </button>
          <button v-if="activeActProb.is_ignored" @click="$emit('unignore', activeActProb.id); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <span>{{ t('inc_btn_unignore') }}</span>
          </button>
          <button v-else @click="$emit('open-ignore-modal', activeActProb); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-amber-950/50 text-amber-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
            <span>{{ t('inc_btn_ignore') }}</span>
          </button>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentTime, formatIncidentDuration, formatIncidentMessage, formatIncidentTip, severityBadgeClass } from '../../utils/formatters'
import { matchesGroupFilter } from '../../utils/filterHelpers'
import { useFloatingDropdown } from '../../utils/useFloatingDropdown'
import NocTablePagination from '../common/NocTablePagination.vue'
import ActiveIncidentsFilterBar from './ActiveIncidentsFilterBar.vue'

const { t, locale } = useI18n()
const { openId: openActId, activeItem: activeActProb, dropdownStyle: actDropdownStyle, toggle: toggleActDropdown, close: closeActDropdown } = useFloatingDropdown(160, 176)

const props = defineProps({
  problems: { type: Array, default: () => [] },
  servers: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null }
})

defineEmits(['ack', 'unignore', 'open-ignore-modal', 'open-workspace'])

const selectedServerId = ref('')
const selectedGroup = ref('')
const activeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

watch([selectedServerId, selectedGroup, activeFilter, searchQuery], () => { currentPage.value = 1 })

function resetFilters() {
  selectedServerId.value = ''
  selectedGroup.value = ''
  activeFilter.value = 'all'
  searchQuery.value = ''
}

const canOperate = computed(() => !['viewer', 'guest', 'tamu'].includes((props.currentUser?.role || '').toLowerCase()))

const scopedProblems = computed(() => {
  return props.problems.filter(p => {
    if (selectedServerId.value && String(p.server_id) !== selectedServerId.value) return false
    if (!matchesGroupFilter(p.group_name, selectedGroup.value)) return false
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      const hay = `${p.hostname || ''} ${p.group_name || ''} ${p.message || ''} ${p.key || ''} ${p.tip || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const pillCounts = computed(() => {
  const base = scopedProblems.value
  const nonIgn = base.filter(p => !p.is_ignored)
  return {
    all: base.length,
    danger: nonIgn.filter(p => (p.severity || '').toLowerCase() === 'danger').length,
    critical: nonIgn.filter(p => ['critical', 'average'].includes((p.severity || '').toLowerCase())).length,
    warning: nonIgn.filter(p => (p.severity || '').toLowerCase() === 'warning').length,
    info: nonIgn.filter(p => !p.severity || p.severity.toLowerCase() === 'info').length,
    ignored: base.filter(p => p.is_ignored).length,
  }
})

const filteredProblems = computed(() => {
  return scopedProblems.value.filter(p => {
    if (activeFilter.value === 'ignored') return Boolean(p.is_ignored)
    if (activeFilter.value === 'all') return true
    if (p.is_ignored) return false
    const sev = (p.severity || 'info').toLowerCase()
    if (activeFilter.value === 'critical') return sev === 'critical' || sev === 'average'
    return sev === activeFilter.value
  })
})

const paginatedProblems = computed(() => {
  if (pageSize.value === 'all') return filteredProblems.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredProblems.value.slice(start, start + limit)
})
</script>
