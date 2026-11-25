<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between mb-2 border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_cron_title') }}</h3>
        <span class="text-xs text-gray-400">({{ filteredJobs.length }} of {{ allJobs.length }} scheduled)</span>
      </div>
    </div>

    <NocFilterPanel
      v-if="allJobs.length > 0"
      :has-active-filters="Boolean(userFilter || search.trim())"
      :summary-text="`${filteredJobs.length} of ${allJobs.length} cron jobs`"
      compact
      @reset="userFilter = ''; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="cron-user-filter">{{ t('ws_col_user') }}</label>
          <select id="cron-user-filter" v-model="userFilter" class="noc-filter-select">
            <option value="">All Users</option>
            <option v-for="u in uniqueUsers" :key="u" :value="u">{{ u }}</option>
          </select>
        </div>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="cron-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="cron-search-input" v-model="search" type="search" placeholder="Search schedule, command, source..." />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="allJobs.length === 0" class="text-xs text-gray-400 py-8 text-center">
      {{ t('ws_cron_empty') }}
    </div>
    <div v-else class="overflow-x-auto max-h-[460px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
          <tr class="text-gray-400 uppercase font-bold tracking-wider">
            <th class="py-2.5 px-3">{{ t('ws_col_schedule') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_exec') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_source') }}</th>
            <th class="py-2.5 px-3 text-right">{{ t('col_actions') || 'Actions' }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(j, idx) in paginatedJobs" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 font-bold text-amber-300 whitespace-nowrap">{{ j.schedule }}</td>
            <td class="py-2.5 px-3 text-gray-300 font-medium whitespace-nowrap">{{ j.user || 'root' }}</td>
            <td class="py-2.5 px-3 text-gray-200 truncate max-w-md cursor-help hover:text-cyan-200" :title="j.command">{{ j.command }}</td>
            <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap">{{ j.source || '-' }}</td>
            <td class="py-2.5 px-3 text-right">
              <button type="button" @click="runCron(j)" class="px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 hover:bg-cyan-900 text-[11px] font-bold transition cursor-pointer" :title="`Execute command on-demand: ${j.command}`">
                Run Now
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredJobs.length" unitLabel="jobs" :pageSizeOptions="[10, 25, 50, 'all']" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()
const props = defineProps({ cronData: { type: Object, default: () => ({ jobs: [] }) } })
const emit = defineEmits(['cron-action'])

const userFilter = ref('')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const allJobs = computed(() => props.cronData?.jobs || [])
const uniqueUsers = computed(() => Array.from(new Set(allJobs.value.map(j => j.user || 'root'))).sort())

watch([userFilter, search], () => { currentPage.value = 1 })

const filteredJobs = computed(() => allJobs.value.filter(j => {
  if (userFilter.value && (j.user || 'root') !== userFilter.value) return false
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    return `${j.schedule || ''} ${j.user || ''} ${j.command || ''} ${j.source || ''}`.toLowerCase().includes(q)
  }
  return true
}))

const paginatedJobs = computed(() => {
  if (pageSize.value === 'all') return filteredJobs.value
  const limit = parseInt(pageSize.value, 10) || 10
  return filteredJobs.value.slice((currentPage.value - 1) * limit, currentPage.value * limit)
})

function runCron(job) {
  if (!confirm(`Run cron command immediately on host:\n\n${job.command}`)) return
  emit('cron-action', { action: 'cron_run', params: { user: job.user || 'root', command: job.command } })
}
</script>
