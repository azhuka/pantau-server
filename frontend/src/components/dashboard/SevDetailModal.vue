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
              <th class="py-2 px-3 text-right">{{ t('sdm_col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-for="p in paginatedList" :key="p.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap">
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
                  {{ p.message }}
                </div>
                <div v-if="p.is_ignored" class="text-[11px] text-amber-400/90 mt-0.5">
                  ({{ t('sdm_ignored_by', { user: p.ignored_by || 'operator' }) }}{{ p.ignored_reason ? ': ' + p.ignored_reason : '' }})
                </div>
              </td>
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    @click="$emit('open-problem-detail', p)"
                    class="px-2 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 hover:bg-cyan-800 hover:text-white transition cursor-pointer font-bold text-[11px]"
                    :title="t('sdm_act_diagnose')"
                  >
                    {{ t('sdm_act_diagnose') }}
                  </button>

                  <button
                    v-if="p.is_ignored"
                    @click="$emit('unignore-problem', p.id)"
                    class="px-2 py-1 rounded bg-amber-950 text-amber-300 border border-amber-700 hover:bg-amber-800 hover:text-white transition cursor-pointer font-bold text-[11px]"
                    :title="t('sdm_act_unignore')"
                  >
                    {{ t('sdm_act_unignore') }}
                  </button>
                  <button
                    v-else
                    @click="$emit('ignore-problem', p)"
                    class="px-2 py-1 rounded bg-gray-900 text-gray-400 border border-gray-700 hover:bg-gray-700 hover:text-white transition cursor-pointer font-bold text-[11px]"
                    :title="t('sdm_act_ignore')"
                  >
                    {{ t('sdm_act_ignore') }}
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

const { t } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  severity: { type: String, default: 'danger' },
  problems: { type: Array, default: () => [] }
})

defineEmits(['close', 'open-problem-detail', 'open-server', 'unignore-problem', 'ignore-problem'])

const search = ref('')
const currentPage = ref(1)
const pageSize = 10

const modalTitle = computed(() => {
  switch (props.severity) {
    case 'danger': return t('sdm_title_danger')
    case 'critical': return t('sdm_title_critical')
    case 'warning': return t('sdm_title_warning')
    case 'info': return t('sdm_title_info')
    case 'ignored': return t('sdm_title_ignored')
    default: return t('sdm_title_default')
  }
})

const dotClass = computed(() => {
  switch (props.severity) {
    case 'danger': return 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]'
    case 'critical': return 'bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.6)]'
    case 'warning': return 'bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.6)]'
    case 'info': return 'bg-cyan-400 shadow-[0_0_8px_rgba(56,189,248,0.6)]'
    default: return 'bg-gray-400'
  }
})

const badgeClass = computed(() => {
  switch (props.severity) {
    case 'danger': return 'bg-rose-950 text-rose-300 border border-rose-800'
    case 'critical': return 'bg-orange-950 text-orange-300 border border-orange-800'
    case 'warning': return 'bg-amber-950 text-amber-300 border border-amber-800'
    case 'info': return 'bg-cyan-950 text-cyan-300 border border-cyan-800'
    default: return 'bg-gray-900 text-gray-300 border border-gray-700'
  }
})

const cardBorderClass = computed(() => {
  switch (props.severity) {
    case 'danger': return 'border-rose-500/50'
    case 'critical': return 'border-orange-500/50'
    case 'warning': return 'border-amber-500/50'
    case 'info': return 'border-cyan-500/50'
    default: return 'border-gray-700'
  }
})

const filteredList = computed(() => {
  let list = props.problems || []
  if (props.severity === 'ignored') {
    list = list.filter(p => p.is_ignored)
  } else {
    list = list.filter(p => !p.is_ignored && (p.severity === props.severity || (props.severity === 'critical' && p.severity === 'average')))
  }
  if (!search.value) return list
  const q = search.value.toLowerCase()
  return list.filter(p =>
    (p.message || '').toLowerCase().includes(q) ||
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
  const d = new Date(isoStr)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>
