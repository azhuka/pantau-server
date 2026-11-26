<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between shadow-lg gap-3 flex-wrap">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>SYSTEM AUDIT TRAIL</span>
          <span v-if="lastSyncTime" class="text-[11px] font-normal text-emerald-400/90 normal-case tracking-normal">
            live · {{ lastSyncTime }}
          </span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">{{ t('audit_subtitle') }}</p>
      </div>

      <button
        type="button"
        @click="loadAuditLogs({ silent: false })"
        class="px-2.5 py-1 text-xs font-mono font-bold rounded bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-800 hover:text-white transition cursor-pointer flex items-center gap-1.5"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/>
        </svg>
        <span>{{ t('audit_reload') }}</span>
      </button>
    </div>

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
      v-model:limit="fetchLimit"
      :total-rows="auditLogs.length"
      :total-count="totalMatched"
      :truncated="isTruncated"
      @reset="resetAuditFilters"
    />

    <!-- Audit Table Card -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl mb-8">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div v-if="loading && auditLogs.length === 0" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_loading') }}
      </div>
      <div v-else-if="auditLogs.length === 0" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_empty') }}
      </div>
      <AuditTable v-else :rows="paginatedLogs" />

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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import { apiFetch } from '../../utils/api'
import NocTablePagination from '../common/NocTablePagination.vue'
import AuditFilterBar from './AuditFilterBar.vue'
import AuditTable from './AuditTable.vue'

const { t } = useI18n()
const loading = ref(false)
const auditLogs = ref([])
const totalMatched = ref(0)
const isTruncated = ref(false)
const lastSyncTime = ref('')
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
const fetchLimit = ref(300)
const currentPage = ref(1)
const pageSize = ref(10)

let debounceTimer = null
let pollTimer = null
let activeController = null

const paginatedLogs = computed(() => {
  if (pageSize.value === 'all') return auditLogs.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return auditLogs.value.slice(start, start + limit)
})

function buildQueryParams() {
  const params = new URLSearchParams({ limit: String(fetchLimit.value), period: filterPeriod.value })
  if (filterUser.value) params.set('user', filterUser.value)
  if (filterServerId.value) params.set('server_id', filterServerId.value)
  if (filterAction.value) params.set('action', filterAction.value)
  if (filterStatus.value) params.set('status', filterStatus.value)
  if (filterStartDate.value) params.set('start_date', filterStartDate.value)
  if (filterEndDate.value) params.set('end_date', filterEndDate.value)
  if (searchKeyword.value.trim()) params.set('q', searchKeyword.value.trim())
  return params
}

function syncUrlQuery() {
  const params = buildQueryParams()
  if (params.get('period') === '24h') params.delete('period')
  if (params.get('limit') === '300') params.delete('limit')
  const qs = params.toString()
  window.history.replaceState(null, '', qs ? `${window.location.pathname}?${qs}` : window.location.pathname)
}

function hydrateFromUrl() {
  const p = new URLSearchParams(window.location.search)
  filterUser.value = p.get('user') || ''
  filterServerId.value = p.get('server_id') || ''
  filterAction.value = p.get('action') || ''
  filterStatus.value = p.get('status') || ''
  filterPeriod.value = p.get('period') || '24h'
  filterStartDate.value = p.get('start_date') || ''
  filterEndDate.value = p.get('end_date') || ''
  searchKeyword.value = p.get('q') || ''
  const lim = Number(p.get('limit'))
  if ([100, 300, 500].includes(lim)) fetchLimit.value = lim
}

watch([filterUser, filterServerId, filterAction, filterStatus, filterPeriod, filterStartDate, filterEndDate, fetchLimit], () => {
  currentPage.value = 1
  if (filterPeriod.value === 'custom' && !filterStartDate.value && !filterEndDate.value) return
  syncUrlQuery()
  loadAuditLogs({ silent: auditLogs.value.length > 0 })
})

watch(searchKeyword, () => {
  currentPage.value = 1
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    syncUrlQuery()
    loadAuditLogs({ silent: auditLogs.value.length > 0 })
  }, 250)
})

function resetAuditFilters() {
  filterUser.value = ''
  filterServerId.value = ''
  filterAction.value = ''
  filterStatus.value = ''
  filterStartDate.value = ''
  filterEndDate.value = ''
  searchKeyword.value = ''
  fetchLimit.value = 300
  filterPeriod.value = '24h'
}

async function loadAuditMeta() {
  try {
    const res = await apiFetch('/api/audit/meta')
    if (res.ok) {
      const m = await res.json()
      metaUsers.value = m.users || []
      metaServers.value = m.servers || []
      metaCategories.value = m.categories || []
    }
  } catch (e) { console.error('Failed to load audit meta:', e) }
}

async function loadAuditLogs({ silent = false } = {}) {
  if (activeController) activeController.abort()
  activeController = new AbortController()
  if (!silent) loading.value = true
  try {
    const res = await apiFetch(`/api/audit?${buildQueryParams().toString()}`, { signal: activeController.signal })
    if (res.ok) {
      const rows = await res.json()
      auditLogs.value = rows
      totalMatched.value = Number(res.headers.get('X-Total-Count') || rows.length)
      isTruncated.value = res.headers.get('X-Truncated') === 'true'
      lastSyncTime.value = new Date().toLocaleTimeString('en-GB', { hour12: false })
    }
  } catch (e) {
    if (e.name !== 'AbortError') console.error('Failed to load audit logs:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  hydrateFromUrl()
  loadAuditMeta()
  loadAuditLogs({ silent: false })
  pollTimer = setInterval(() => {
    if (!document.hidden) loadAuditLogs({ silent: true })
  }, 5000)
})

onUnmounted(() => {
  clearTimeout(debounceTimer)
  clearInterval(pollTimer)
  if (activeController) activeController.abort()
})
</script>