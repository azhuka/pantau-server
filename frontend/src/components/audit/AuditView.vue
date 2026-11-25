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

    <!-- Filter & Search Toolbar Card -->
    <div class="p-3.5 px-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 flex items-center justify-between flex-wrap gap-3 font-mono text-xs">
      <div class="flex items-center gap-3 flex-wrap flex-1">
        <!-- Period Filter -->
        <div class="flex items-center gap-1.5">
          <span class="text-gray-400 text-[11px]">{{ t('audit_period') }}</span>
          <select
            v-model="filterPeriod"
            @change="loadAuditLogs"
            class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
          >
            <option value="24h">{{ t('audit_period_24h') }}</option>
            <option value="today">{{ t('audit_period_today') }}</option>
            <option value="7d">{{ t('audit_period_7d') }}</option>
            <option value="30d">{{ t('audit_period_30d') }}</option>
            <option value="all">{{ t('audit_period_all') }}</option>
          </select>
        </div>

        <!-- Status Filter -->
        <div class="flex items-center gap-1.5">
          <span class="text-gray-400 text-[11px]">{{ t('audit_filter_status') }}</span>
          <select
            v-model="filterStatus"
            @change="loadAuditLogs"
            class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
          >
            <option value="">{{ t('audit_status_all') }}</option>
            <option value="SUCCESS">{{ t('audit_status_success') }}</option>
            <option value="FAILED">{{ t('audit_status_failed') }}</option>
          </select>
        </div>

        <!-- Limit -->
        <div class="flex items-center gap-1.5">
          <span class="text-gray-400 text-[11px]">{{ t('audit_limit') }}</span>
          <select
            v-model="filterLimit"
            @change="loadAuditLogs"
            class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
          >
            <option :value="50">50 {{ t('audit_limit_rows', { count: '' }).trim() }}</option>
            <option :value="100">100 {{ t('audit_limit_rows', { count: '' }).trim() }}</option>
            <option :value="200">200 {{ t('audit_limit_rows', { count: '' }).trim() }}</option>
            <option :value="500">500 {{ t('audit_limit_rows', { count: '' }).trim() }}</option>
          </select>
        </div>
      </div>

      <!-- Search Input -->
      <div class="w-full sm:w-64">
        <input
          v-model="searchKeyword"
          @keyup.enter="loadAuditLogs"
          type="search"
          :placeholder="t('audit_search_placeholder')"
          class="w-full bg-[#111827] border border-gray-800 rounded px-3 py-1 text-xs text-gray-200 focus:border-cyan-500 outline-none"
        />
      </div>
    </div>

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
                  {{ log.action }}
                </span>
              </td>
              <td
                class="py-2.5 px-4 text-gray-300 truncate max-w-xs cursor-help hover:text-cyan-300"
                :title="log.target"
              >
                {{ log.target }}
              </td>
              <td class="py-2.5 px-4 text-center whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-bold border"
                  :class="isResultSuccess(log.result) ? 'bg-emerald-950 text-emerald-300 border-emerald-800' : 'bg-rose-950 text-rose-300 border-rose-800'"
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

const { t } = useI18n()

const loading = ref(false)
const auditLogs = ref([])

const filterPeriod = ref('24h')
const filterStatus = ref('')
const filterLimit = ref(50)
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const paginatedLogs = computed(() => {
  if (pageSize.value === 'all') return auditLogs.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return auditLogs.value.slice(start, start + limit)
})

watch([filterPeriod, filterStatus, filterLimit, searchKeyword], () => {
  currentPage.value = 1
})

async function loadAuditLogs() {
  loading.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const params = new URLSearchParams({
      limit: String(filterLimit.value),
      period: filterPeriod.value,
    })
    if (filterStatus.value) params.set('status', filterStatus.value)
    if (searchKeyword.value.trim()) params.set('q', searchKeyword.value.trim())

    const res = await fetch(`/api/audit?${params.toString()}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    if (res.ok) {
      auditLogs.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load audit logs:', e)
  } finally {
    loading.value = false
  }
}

function isResultSuccess(res) {
  if (!res) return true
  const lower = String(res).toLowerCase()
  return !(lower.includes('fail') || lower.includes('gagal') || lower.includes('error'))
}

function getActionBadgeClass(action) {
  const act = String(action).toLowerCase()
  if (act.includes('delete') || act.includes('rm') || act.includes('kill') || act.includes('block') || act.includes('lock')) {
    return 'bg-rose-950/80 text-rose-300 border-rose-800'
  }
  if (act.includes('add') || act.includes('create') || act.includes('start') || act.includes('unlock') || act.includes('enable')) {
    return 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
  }
  if (act.includes('update') || act.includes('upgrade') || act.includes('restart') || act.includes('reset')) {
    return 'bg-amber-950/80 text-amber-300 border-amber-800'
  }
  return 'bg-cyan-950 text-cyan-300 border-cyan-800'
}

onMounted(() => {
  loadAuditLogs()
})
</script>
