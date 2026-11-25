<template>
  <div class="space-y-4 font-mono">
    <!-- Active Remote SSH Sessions -->
    <div class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_ssh_active_title') }}</h3>
        <span v-if="(activeSSHSessions || []).length > 0" class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 radar-warning">
          {{ activeSSHSessions.length }} {{ t('ws_ssh_sessions_count') }}
        </span>
      </div>
      <div v-if="(activeSSHSessions || []).length === 0" class="text-xs text-gray-400 py-6 text-center">
        {{ t('ws_ssh_empty') }}
      </div>
      <div v-else class="space-y-2">
        <div v-for="(s, idx) in activeSSHSessions" :key="idx" class="p-3 bg-amber-950/20 border border-amber-700/60 rounded-lg flex items-center justify-between">
          <div class="flex items-center gap-3">
            <svg class="w-5 h-5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21 2-2 2m-1.5 1.5L14 9l-2-2-4 4 2 2-3 3-2-2-3 3v4h4l3-3-2-2 3-3 2 2 4-4-2-2 3.5-3.5Z"/></svg>
            <div>
              <div class="text-xs font-bold text-amber-300">{{ s.user }} <span class="text-gray-400 font-normal">{{ t('ws_connected_from') }}</span> {{ s.from }}</div>
              <div class="text-xs text-gray-400 mt-1">TTY: {{ s.tty }} · {{ t('dash_col_time') }}: {{ s.time || '-' }}</div>
            </div>
          </div>
          <button @click="$emit('terminate-ssh', s.user, s.tty)" class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white font-bold text-xs transition cursor-pointer flex items-center gap-1.5" :title="`Terminate active SSH session for user ${s.user} on ${s.tty}`">
            <span>{{ t('ws_sever_ssh_btn') }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Local User Accounts + Multi-Filter -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_accounts_title') }}</h3>

      <NocFilterPanel
        v-if="(accountsList || []).length > 0"
        :has-active-filters="Boolean(shellFilter || search.trim())"
        :summary-text="`${filteredAccounts.length} of ${accountsList.length} accounts`"
        compact
        @reset="shellFilter = ''; search = ''"
      >
        <template #fields>
          <div class="noc-filter-col">
            <label class="noc-filter-label" for="acc-shell-filter">{{ t('ws_col_shell') }}</label>
            <select id="acc-shell-filter" v-model="shellFilter" class="noc-filter-select">
              <option value="">All Shells</option>
              <option value="login">Interactive Login Shell</option>
              <option value="nologin">Non-Login (nologin / false)</option>
            </select>
          </div>
          <div class="noc-filter-col-search">
            <label class="noc-filter-label" for="acc-search-input">{{ t('flt_search') }}</label>
            <div class="noc-filter-search-box">
              <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input id="acc-search-input" v-model="search" type="search" placeholder="Search username, UID, home, shell..." />
            </div>
          </div>
        </template>
      </NocFilterPanel>

      <div class="overflow-x-auto max-h-[380px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
            <tr class="text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('ws_col_username') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_uid') || 'UID' }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_home') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_shell') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(acc, idx) in paginatedAccounts" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 px-3 font-semibold text-gray-200">{{ acc.user || acc.name }}</td>
              <td class="py-2.5 px-3 text-gray-400">{{ acc.uid ?? '-' }}</td>
              <td class="py-2.5 px-3 text-gray-300">{{ acc.home || '-' }}</td>
              <td class="py-2.5 px-3 text-cyan-400">{{ acc.shell || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredAccounts.length" unitLabel="accounts" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()
const props = defineProps({
  activeSSHSessions: { type: Array, default: () => [] },
  accountsList: { type: Array, default: () => [] }
})
defineEmits(['terminate-ssh'])

const shellFilter = ref('')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

watch([shellFilter, search], () => { currentPage.value = 1 })

const filteredAccounts = computed(() => (props.accountsList || []).filter(acc => {
  const sh = String(acc.shell || '').toLowerCase()
  const isNoLogin = !sh || sh.includes('nologin') || sh.endsWith('/false') || sh.endsWith('/sync')
  if (shellFilter.value === 'login' && isNoLogin) return false
  if (shellFilter.value === 'nologin' && !isNoLogin) return false
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    return `${acc.user || acc.name || ''} ${acc.uid ?? ''} ${acc.home || ''} ${acc.shell || ''}`.toLowerCase().includes(q)
  }
  return true
}))

const paginatedAccounts = computed(() => {
  if (pageSize.value === 'all') return filteredAccounts.value
  const limit = parseInt(pageSize.value, 10) || 10
  return filteredAccounts.value.slice((currentPage.value - 1) * limit, currentPage.value * limit)
})
</script>
