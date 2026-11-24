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

        <!-- Filter Pills & Search -->
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <div class="flex items-center bg-[#060a14] p-0.5 rounded border border-gray-800">
            <button
              v-for="sev in ['all', 'danger', 'critical', 'warning', 'info', 'ignored']"
              :key="sev"
              @click="activeFilter = sev"
              class="px-2.5 py-1 rounded text-[11px] font-bold uppercase transition cursor-pointer"
              :class="activeFilter === sev ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : 'text-gray-400 hover:text-gray-200'"
            >
              {{ t(`inc_filter_${sev}`) }}
            </button>
          </div>

          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('inc_search_placeholder')"
            class="bg-[#060a14] border border-gray-800 focus:border-cyan-500 rounded px-2.5 py-1 text-xs text-gray-200 placeholder-gray-500 focus:outline-none w-48"
          />
        </div>
      </div>

      <!-- Table Content -->
      <div class="overflow-x-auto mt-2">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('inc_col_start') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_asset') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_sev') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_event') }}</th>
              <th class="py-2.5 px-3">{{ t('inc_col_durasi') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('inc_col_tindakan') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-if="paginatedProblems.length === 0">
              <td colspan="6" class="py-8 text-center text-gray-500 italic">
                {{ problems.length === 0 ? t('inc_empty_active') : t('inc_empty_filtered') }}
              </td>
            </tr>
            <tr
              v-for="prob in paginatedProblems"
              :key="prob.id"
              class="hover:bg-cyan-950/20 transition-colors group"
            >
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap" :title="prob.started_at || prob.created_at">
                {{ formatIncidentTime(prob.started_at || prob.created_at) }}
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="font-bold text-cyan-300">{{ prob.hostname || `Server #${prob.server_id}` }}</span>
              </td>
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
                    <span>✓</span>
                    <span>{{ t('dash_badge_handled') }}</span>
                  </span>
                </div>
              </td>
              <td class="py-2.5 px-3 text-gray-200">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-medium">{{ formatIncidentMessage(prob, locale) }}</span>
                  <span
                    v-if="prob.acknowledged_by"
                    class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1"
                    :title="`Handled by ${prob.acknowledged_by} at ${prob.acknowledged_at || '-'}`"
                  >
                    ✓ {{ t('inc_ack_badge') }}: {{ prob.acknowledged_by }}
                  </span>
                  <span
                    v-if="prob.is_ignored"
                    class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-gray-700/50 text-gray-300 border border-gray-600 flex items-center gap-1"
                    :title="prob.ignored_reason || 'Ignored'"
                  >
                    🔇 {{ t('inc_ignored_badge') }} {{ formatIncidentTime(prob.ignored_until) }}
                  </span>
                </div>
              </td>
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap">
                {{ formatIncidentDuration(prob.started_at || prob.created_at, locale) }}
              </td>
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <div class="inline-flex items-center justify-end gap-1.5">
                  <!-- Minor Action: Tandai Ditangani (Acknowledge) -->
                  <button
                    v-if="canOperate && !prob.acknowledged_by"
                    @click="$emit('ack', prob.id)"
                    class="px-2.5 py-1 rounded bg-emerald-950/40 hover:bg-emerald-900/60 text-emerald-300 border border-emerald-600/40 font-bold text-[11px] transition cursor-pointer flex items-center gap-1 shadow-sm"
                    :title="t('inc_btn_ack')"
                  >
                    <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>{{ t('inc_btn_ack') }}</span>
                  </button>

                  <!-- Status: Sudah Ditangani (Hover untuk Batal Ditangani) -->
                  <button
                    v-else-if="canOperate && prob.acknowledged_by"
                    @click="$emit('unack', prob.id)"
                    class="px-2 py-1 rounded bg-emerald-950/30 hover:bg-rose-950/40 text-emerald-300 hover:text-rose-300 border border-emerald-600/40 hover:border-rose-600/40 font-bold text-[10px] transition cursor-pointer flex items-center gap-1 group/ack"
                    :title="`${t('inc_ack_badge')}: ${prob.acknowledged_by} (${formatIncidentTime(prob.acknowledged_at)}) — ${t('inc_btn_unack')}`"
                  >
                    <svg class="w-3 h-3 text-emerald-400 group-hover/ack:text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    <span class="group-hover/ack:hidden">✓ {{ prob.acknowledged_by }}</span>
                    <span class="hidden group-hover/ack:inline text-rose-300">{{ t('inc_btn_unack') }}</span>
                  </button>

                  <!-- Minor Action: Abaikan / Pantau Kembali -->
                  <button
                    v-if="canOperate && prob.is_ignored"
                    @click="$emit('unignore', prob.id)"
                    class="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-600 font-bold text-[11px] transition cursor-pointer flex items-center gap-1"
                    :title="t('inc_btn_unignore')"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    <span>{{ t('inc_btn_unignore') }}</span>
                  </button>
                  <button
                    v-else-if="canOperate && !prob.is_ignored"
                    @click="$emit('open-ignore-modal', prob)"
                    class="px-2 py-1 rounded bg-amber-950/30 hover:bg-amber-900/50 text-amber-300 border border-amber-600/30 font-bold text-[11px] transition cursor-pointer flex items-center gap-1"
                    :title="t('inc_btn_ignore')"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
                    <span>{{ t('inc_btn_ignore') }}</span>
                  </button>

                  <!-- Major Remediation: Open Asset Details Modal -->
                  <button
                    @click="$emit('open-workspace', { server_id: prob.server_id, problem: prob })"
                    class="px-2.5 py-1 rounded bg-cyan-950/50 hover:bg-cyan-900/70 text-cyan-300 border border-cyan-500/50 font-bold text-[11px] transition cursor-pointer flex items-center gap-1"
                    :title="t('inc_btn_workspace')"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    <span>{{ t('inc_btn_workspace') }}</span>
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
import { formatIncidentTime, formatIncidentDuration, formatIncidentMessage } from '../../utils/formatters'

const { t, locale } = useI18n()

const props = defineProps({
  problems: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null }
})

defineEmits(['ack', 'unack', 'unignore', 'open-ignore-modal', 'open-workspace'])

const activeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 10

const canOperate = computed(() => {
  const r = (props.currentUser?.role || '').toLowerCase()
  return !['viewer', 'guest', 'tamu'].includes(r)
})

function severityBadgeClass(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'danger') return 'bg-red-500/20 text-red-400 border-red-500/30'
  if (s === 'critical') return 'bg-orange-500/20 text-orange-400 border-orange-500/30'
  if (s === 'warning') return 'bg-amber-500/20 text-amber-400 border-amber-500/30'
  return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
}

const filteredProblems = computed(() => {
  return props.problems.filter(p => {
    if (activeFilter.value === 'ignored') {
      if (!p.is_ignored) return false
    } else if (activeFilter.value !== 'all') {
      if ((p.severity || '').toLowerCase() !== activeFilter.value) return false
    }

    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      const matchHost = (p.hostname || '').toLowerCase().includes(q)
      const matchMsg = (p.message || '').toLowerCase().includes(q)
      const matchKey = (p.key || '').toLowerCase().includes(q)
      if (!matchHost && !matchMsg && !matchKey) return false
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