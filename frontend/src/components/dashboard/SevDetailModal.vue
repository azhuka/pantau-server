<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
    @click.self="$emit('close')"
  >
    <div class="hud-tactical-card rounded-xl max-w-4xl w-full max-h-[85vh] flex flex-col shadow-2xl border" :class="cardBorderClass">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Modal Header -->
      <div class="p-4 border-b border-gray-800 flex items-center justify-between shrink-0 bg-[#070c18]">
        <div class="flex items-center gap-2.5">
          <span class="w-3 h-3 rounded-full shrink-0" :class="dotClass"></span>
          <h2 class="text-sm font-bold tracking-wider uppercase text-gray-200">
            // {{ modalTitle }}
          </h2>
          <span class="text-xs px-2 py-0.5 rounded font-bold" :class="badgeClass">
            {{ filteredList.length }} {{ t('dash_kpi_total') || 'Incidents' }}
          </span>
        </div>

        <div class="flex items-center gap-2">
          <input
            v-model="search"
            type="text"
            :placeholder="t('sdm_filter_placeholder')"
            class="bg-[#0b1324] border border-gray-700 focus:border-cyan-400 text-gray-200 text-xs rounded px-2.5 py-1 w-48 focus:outline-none"
          />
          <button
            @click="$emit('close')"
            class="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-white transition cursor-pointer"
            :title="t('btn_close') || 'Close'"
          >
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Modal Body (Table) -->
      <div class="p-4 overflow-y-auto flex-1 text-xs">
        <div v-if="filteredList.length === 0" class="py-12 text-center text-gray-500 font-mono">
          {{ t('sdm_empty') }}
        </div>

        <table v-else class="w-full text-left border-collapse font-mono">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-gray-800 text-gray-400 font-bold uppercase text-[11px]">
            <tr>
              <th class="py-2 px-3">{{ t('sdm_col_time') }}</th>
              <th class="py-2 px-3">{{ t('sdm_col_target') }}</th>
              <th class="py-2 px-3">{{ t('sdm_col_incident') }}</th>
              <th class="py-2 px-3 text-center w-24">{{ t('sdm_col_duration') }}</th>
              <th class="py-2 px-3 text-right w-24">{{ t('sdm_col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-for="p in paginatedList" :key="p.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap cursor-help hover:text-cyan-300 transition" :title="formatFullTime(p.started_at)">
                {{ formatTime(p.started_at) }}
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <button
                  @click="$emit('open-server', p.server_id)"
                  class="text-cyan-400 hover:text-cyan-300 font-bold hover:underline cursor-pointer"
                  :title="t('pdm_btn_open_workspace')"
                >
                  {{ p.hostname || `Server #${p.server_id}` }}
                </button>
              </td>
              <td class="py-2.5 px-3">
                <div class="text-gray-200 font-medium leading-relaxed">
                  {{ formatIncidentMessage(p, locale) }}
                </div>
                <div v-if="p.is_ignored" class="text-[11px] text-amber-400/90 mt-0.5">
                  ({{ t('sdm_ignored_by', { user: p.ignored_by || 'operator' }) }}{{ p.ignored_reason ? ': ' + p.ignored_reason : '' }})
                </div>
              </td>
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span class="px-2 py-0.5 rounded bg-gray-900 border border-gray-700/80 font-mono font-bold text-[11px] text-gray-300">
                  {{ calcDuration(p.started_at) }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <div class="flex items-center justify-end gap-1.5">
                  <!-- Tombol Tandai Ditangani (Ack) -->
                  <button
                    v-if="!p.acknowledged_by && !isViewer"
                    @click="$emit('ack-problem', p.id)"
                    class="p-1.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-700/80 hover:bg-emerald-800 hover:text-white transition cursor-pointer"
                    :title="t('inc_btn_ack')"
                    :aria-label="t('inc_btn_ack')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  </button>

                  <button
                    @click="$emit('open-problem-detail', p)"
                    class="p-1.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/80 hover:bg-cyan-800 hover:text-white transition cursor-pointer"
                    :title="t('sdm_act_diagnose_tooltip')"
                    :aria-label="t('sdm_act_diagnose')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                  </button>

                  <button
                    v-if="p.is_ignored && !isViewer"
                    @click="$emit('unignore-problem', p.id)"
                    class="p-1.5 rounded bg-amber-950/80 text-amber-400 border border-amber-700/80 hover:bg-amber-800 hover:text-white transition cursor-pointer"
                    :title="t('sdm_act_unignore_tooltip')"
                    :aria-label="t('sdm_act_unignore')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                    </svg>
                  </button>
                  <button
                    v-else-if="!isViewer"
                    @click="$emit('ignore-problem', p)"
                    class="p-1.5 rounded bg-gray-900 text-gray-400 border border-gray-700/80 hover:bg-gray-800 hover:text-amber-400 transition cursor-pointer"
                    :title="t('sdm_act_ignore_tooltip')"
                    :aria-label="t('sdm_act_ignore')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M13.73 21a2 2 0 0 1-3.46 0"/><path d="M18.63 13A17.89 17.89 0 0 1 18 8"/><path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/><path d="M18 8a6 6 0 0 0-9.33-5"/><line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Modal Footer -->
      <div v-if="totalPages > 1" class="p-3 border-t border-gray-800 flex items-center justify-between text-xs text-gray-400 bg-[#070c18]">
        <span>{{ t('sdm_page_info', { current: currentPage, total: totalPages }) }}</span>
        <div class="flex items-center gap-1">
          <button
            :disabled="currentPage === 1"
            @click="currentPage--"
            class="px-2.5 py-1 rounded bg-gray-900 border border-gray-800 disabled:opacity-30 cursor-pointer"
          >
            {{ t('sdm_prev') }}
          </button>
          <button
            :disabled="currentPage === totalPages"
            @click="currentPage++"
            class="px-2.5 py-1 rounded bg-gray-900 border border-gray-800 disabled:opacity-30 cursor-pointer"
          >
            {{ t('sdm_next') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentMessage, formatIncidentDuration } from '../../utils/formatters'

const { t, locale } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  severity: { type: String, default: 'danger' },
  problems: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null }
})

defineEmits(['close', 'open-problem-detail', 'open-server', 'unignore-problem', 'ignore-problem', 'ack-problem'])

const isViewer = computed(() => {
  const r = (props.currentUser?.role || '').toLowerCase()
  return !props.currentUser || ['viewer', 'guest', 'tamu'].includes(r)
})

const search = ref('')
const currentPage = ref(1)
const pageSize = 10

const TITLES = { danger: 'sdm_title_danger', critical: 'sdm_title_critical', warning: 'sdm_title_warning', info: 'sdm_title_info', ignored: 'sdm_title_ignored' }
const modalTitle = computed(() => t(TITLES[props.severity] || 'sdm_title_default'))

const DOTS = { danger: 'bg-rose-500 radar-critical', critical: 'bg-orange-500 radar-critical', warning: 'bg-amber-400 radar-warning', info: 'bg-cyan-400', ignored: 'bg-slate-400' }
const dotClass = computed(() => DOTS[props.severity] || 'bg-gray-400')

const BADGES = { danger: 'bg-rose-950 text-rose-300 border border-rose-800', critical: 'bg-orange-950 text-orange-300 border border-orange-800', warning: 'bg-amber-950 text-amber-300 border border-amber-800', info: 'bg-cyan-950 text-cyan-300 border border-cyan-800', ignored: 'bg-slate-900 text-slate-300 border border-slate-700' }
const badgeClass = computed(() => BADGES[props.severity] || 'bg-gray-900 text-gray-300 border border-gray-700')

const BORDERS = { danger: 'border-rose-500/50', critical: 'border-orange-500/50', warning: 'border-amber-500/50', info: 'border-cyan-500/50', ignored: 'border-slate-500/50' }
const cardBorderClass = computed(() => BORDERS[props.severity] || 'border-gray-700')

const filteredList = computed(() => {
  let list = props.problems || []
  if (props.severity === 'ignored') {
    list = list.filter(p => p.is_ignored)
  } else {
    list = list.filter(p => (p.is_active || !p.resolved_at) && !p.is_ignored && (
      p.severity === props.severity ||
      (props.severity === 'critical' && p.severity === 'average') ||
      (props.severity === 'info' && (!p.severity || p.severity === 'info'))
    ))
  }
  if (!search.value) return list
  const q = search.value.toLowerCase()
  return list.filter(p =>
    (formatIncidentMessage(p, locale) || p.message || '').toLowerCase().includes(q) ||
    (p.hostname || '').toLowerCase().includes(q)
  )
})

const totalPages = computed(() => Math.ceil(filteredList.value.length / pageSize) || 1)

const paginatedList = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredList.value.slice(start, start + pageSize)
})

function formatTime(isoStr) {
  if (!isoStr) return '—'
  return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatFullTime(isoStr) {
  if (!isoStr) return '—'
  try { return new Date(isoStr).toLocaleString() } catch { return isoStr }
}

function calcDuration(startedAt) {
  return formatIncidentDuration(startedAt, locale)
}
</script>
