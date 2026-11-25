<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// SYSTEM AUDIT TRAIL</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('audit_subtitle') }}
        </p>
      </div>

      <button
        @click="loadAuditLogs"
        class="px-2.5 py-1 text-xs font-mono font-bold rounded bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-800 hover:text-white transition cursor-pointer flex items-center gap-1.5"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
          <path d="M16 21h5v-5"/>
        </svg>
        <span>{{ t('audit_reload') }}</span>
      </button>
    </div>

    <!-- Filter & Search Toolbar (Blueprint Multi-Criteria + Quick Presets) -->
    <AuditFilterBar
      :users="metaUsers"
      :servers="metaServers"
      :categories="metaCategories"
      v-model:user="filterUser"
      v-model:serverId="filterServerId"
      v-model:action="filterAction"
      v-model:status="filterStatus"
      v-model:period="filterPeriod"
      v-model:startDate="filterStartDate"
      v-model:endDate="filterEndDate"
      v-model:search="searchKeyword"
      :total-rows="auditLogs.length"
      @reset="resetAuditFilters"
    />

    <!-- Audit Table Card -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl mb-8">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div v-if="loading" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_loading') }}
      </div>
      <div v-else-if="auditLogs.length === 0" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_empty') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider select-none">
              <th class="py-2.5 px-4 w-36">{{ t('audit_col_time') }}</th>
              <th class="py-2.5 px-4 w-32">{{ t('audit_col_operator') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_target') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_action') }}</th>
              <th class="py-2.5 px-4">{{ t('audit_col_param') }}</th>
              <th class="py-2.5 px-4 w-28 text-center">{{ t('audit_col_status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr v-for="log in paginatedLogs" :key="log.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">{{ log.created_at || '-' }}</td>
              <td class="py-2.5 px-4 font-bold text-gray-100 whitespace-nowrap">{{ log.username }}</td>
              <td class="py-2.5 px-4 text-cyan-400 whitespace-nowrap font-semibold">{{ log.server_name }}</td>
              <td class="py-2.5 px-4 whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-bold border"
                  :class="getActionBadgeClass(log.action)"
                >
                  {{ log.action_label || log.action }}
                </span>
              </td>
              <td
                class="py-2.5 px-4 text-gray-300 truncate max-w-xs cursor-help hover:text-cyan-300"
                :title="`${log.target}${log.result_detail && log.result_detail !== log.result ? ' — ' + log.result_detail : ''}`"
              >
                {{ log.target }}
              </td>
              <td class="py-2.5 px-4 text-center whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-bold border"
                  :class="statusBadgeClass(log.result)"
                  :title="log.result_detail || log.result"
                >
                  {{ log.result || 'SUCCESS' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Universal Table Pagination Bar (Hidden if <= 10 items) -->
      <NocTablePagination
        v-model:page="currentPage"
        v-model:pageSize="pageSize"
        :total="auditLogs.length"
        unitLabel="activities"
        :pageSizeOptions="[10, 25, 50, 100, 'all']"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from '../../i18n'
import NocTablePagination from '../common/NocTablePagination.vue'
import AuditFilterBar from './AuditFilterBar.vue'

const { t } = useI18n()

const loading = ref(false)
const auditLogs = ref([])
const metaUsers = ref([])
const metaServers = ref([])
const metaCategories = ref([])

const filterUser = ref('')
const filterServerId = ref('')
const filterAction = ref('')
const filterStatus = ref('')
const filterPeriod = ref('24h')
const filterStartDate = ref('')
const filterEndDate = ref('')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

let debounceTimer = null

const paginatedLogs = computed(() => {
  if (pageSize.value === 'all') return auditLogs.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return auditLogs.value.slice(start, start + limit)
})

watch([filterUser, filterServerId, filterAction, filterStatus, filterPeriod, filterStartDate, filterEndDate], () => {
  currentPage.value = 1
  if (filterPeriod.value === 'custom' && !filterStartDate.value && !filterEndDate.value) return
  loadAuditLogs()
})

watch(searchKeyword, () => {
  currentPage.value = 1
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadAuditLogs(), 250)
})

function resetAuditFilters() {
  filterUser.value = ''
  filterServerId.value = ''
  filterAction.value = ''
  filterStatus.value = ''
  filterStartDate.value = ''
  filterEndDate.value = ''
  searchKeyword.value = ''
  filterPeriod.value = '24h'
}

async function loadAuditMeta() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/audit/meta', { headers: { Authorization: `Bearer ${token}` } })
    if (res.ok) {
      const m = await res.json()
      metaUsers.value = m.users || []
      metaServers.value = m.servers || []
      metaCategories.value = m.categories || []
    }
  } catch (e) { console.error('Failed to load audit meta:', e) }
}

async function loadAuditLogs() {
  loading.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const params = new URLSearchParams({ limit: '300', period: filterPeriod.value })
    if (filterUser.value) params.set('user', filterUser.value)
    if (filterServerId.value) params.set('server_id', filterServerId.value)
    if (filterAction.value) params.set('action', filterAction.value)
    if (filterStatus.value) params.set('status', filterStatus.value)
    if (filterStartDate.value) params.set('start_date', filterStartDate.value)
    if (filterEndDate.value) params.set('end_date', filterEndDate.value)
    if (searchKeyword.value.trim()) params.set('q', searchKeyword.value.trim())

    const res = await fetch(`/api/audit?${params.toString()}`, { headers: { Authorization: `Bearer ${token}` } })
    if (res.ok) auditLogs.value = await res.json()
  } catch (e) {
    console.error('Failed to load audit logs:', e)
  } finally {
    loading.value = false
  }
}

function statusBadgeClass(res) {
  const up = String(res || '').toUpperCase()
  if (up === 'FAILED') return 'bg-rose-950 text-rose-300 border-rose-800'
  if (up === 'PENDING') return 'bg-amber-950 text-amber-300 border-amber-800'
  return 'bg-emerald-950 text-emerald-300 border-emerald-800'
}

function getActionBadgeClass(action) {
  const act = String(action).toLowerCase()
  if (act.includes('delete') || act.includes('rm') || act.includes('kill') || act.includes('block') || act.includes('lock') || act.includes('poweroff') || act.includes('terminate')) {
    return 'bg-rose-950/80 text-rose-300 border-rose-800'
  }
  if (act.includes('add') || act.includes('create') || act.includes('start') || act.includes('unlock') || act.includes('enable')) {
    return 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
  }
  if (act.includes('update') || act.includes('upgrade') || act.includes('restart') || act.includes('reset') || act.includes('maintenance')) {
    return 'bg-amber-950/80 text-amber-300 border-amber-800'
  }
  return 'bg-cyan-950 text-cyan-300 border-cyan-800'
}

onMounted(() => {
  loadAuditMeta()
  loadAuditLogs()
})
</script>
