<template>
  <div class="space-y-4 font-mono">
    <!-- Sub-Toggle Switcher & Clickable Status Badges -->
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-xs">
        <button
          @click="mode = 'services'"
          class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
          :class="mode === 'services' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span>Systemd Services ({{ filteredServices.length }})</span>
        </button>
        <button
          @click="mode = 'ports'"
          class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
          :class="mode === 'ports' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <span>Listening Ports ({{ (ports || []).length }})</span>
        </button>
      </div>

      <div v-if="mode === 'services'" class="flex items-center gap-2 text-xs">
        <button
          type="button"
          @click="statusFilter = statusFilter === 'running' ? 'all' : 'running'"
          class="px-2 py-0.5 rounded border text-[11px] font-bold transition cursor-pointer"
          :class="statusFilter === 'running' ? 'bg-emerald-950 text-emerald-200 border-emerald-400' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60 hover:border-emerald-500'"
          title="Filter running services (click again to show all)"
        >
          {{ runningCount }} running
        </button>
        <button
          v-if="failedCount > 0"
          type="button"
          @click="statusFilter = statusFilter === 'failed' ? 'all' : 'failed'"
          class="px-2 py-0.5 rounded border text-[11px] font-bold transition cursor-pointer"
          :class="statusFilter === 'failed' ? 'bg-rose-950 text-rose-200 border-rose-400' : 'bg-rose-950/40 text-rose-300 border-rose-800/60 hover:border-rose-500'"
          title="Filter failed services"
        >
          {{ failedCount }} failed
        </button>
      </div>
    </div>

    <!-- View A: Systemd Services Table + Multi-Filter -->
    <div v-if="mode === 'services'" class="hud-tactical-card rounded-xl p-4 space-y-3">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <NocFilterPanel
        :has-active-filters="Boolean(statusFilter !== 'all' || bootFilter !== 'all' || search.trim())"
        :summary-text="`${filteredServices.length} of ${(services || []).length} units`"
        compact
        @reset="statusFilter = 'all'; bootFilter = 'all'; search = ''"
      >
        <template #fields>
          <div class="noc-filter-col-search">
            <label class="noc-filter-label" for="sysd-search-input">{{ t('flt_search') }}</label>
            <div class="noc-filter-search-box">
              <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input id="sysd-search-input" v-model="search" type="search" :placeholder="t('ws_services_search')" />
            </div>
          </div>
          <div class="noc-filter-col">
            <label class="noc-filter-label" for="sysd-status-filter">{{ t('flt_status') }}</label>
            <select id="sysd-status-filter" v-model="statusFilter" class="noc-filter-select">
              <option value="all">{{ t('flt_all_statuses') }}</option>
              <option value="running">running (active)</option>
              <option value="exited">exited (active)</option>
              <option value="failed">failed</option>
              <option value="inactive">inactive (stopped)</option>
            </select>
          </div>
          <div class="noc-filter-col">
            <label class="noc-filter-label" for="sysd-boot-filter">{{ t('flt_boot') }}</label>
            <select id="sysd-boot-filter" v-model="bootFilter" class="noc-filter-select">
              <option value="all">{{ t('flt_all_boot') }}</option>
              <option value="enabled">enabled (auto)</option>
              <option value="disabled">disabled (manual)</option>
              <option value="static">static / masked</option>
            </select>
          </div>
        </template>
      </NocFilterPanel>

      <div class="overflow-x-auto max-h-[460px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
            <tr class="text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('ws_col_service_name') }}</th>
              <th class="py-2.5 px-3">{{ t('col_status') }}</th>
              <th class="py-2.5 px-3">{{ t('flt_boot') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_description') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-if="paginatedServices.length === 0">
              <td colspan="5" class="py-8 text-center text-gray-500 italic">No service units match the selected filters.</td>
            </tr>
            <tr v-for="(svc, idx) in paginatedServices" :key="(svc.name || svc.unit) + idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 px-3 font-semibold text-gray-200 whitespace-nowrap">{{ svc.name || svc.unit }}</td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[11px] uppercase font-bold" :class="svcBadgeClass(svc)">
                  {{ svc.sub || svc.status || svc.active || 'unknown' }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap text-[11px]">{{ svc.boot || '-' }}</td>
              <td class="py-2.5 px-3 text-gray-400 truncate max-w-xs" :title="svc.description || ''">{{ svc.description || '-' }}</td>
              <td class="py-2.5 px-3 text-right">
                <button
                  type="button"
                  @click.stop="toggleSvcDropdown(svc, $event)"
                  class="w-[26px] h-[26px] min-w-[26px] p-0 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 transition cursor-pointer inline-flex items-center justify-center"
                  :title="t('col_actions')"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredServices.length" unitLabel="services" :pageSizeOptions="[10, 25, 50, 100, 'all']" />
    </div>

    <!-- View B: Listening Ports & Sockets Table -->
    <WorkspacePortsTable v-else :ports="ports" />

    <!-- Floating Service Action Dropdown Menu -->
    <Teleport to="body">
      <div v-if="openSvcId && activeSvc" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div class="py-0.5">
          <button type="button" @click="handleAction('restart_service', activeSvc.name || activeSvc.unit)" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition font-bold">Restart</button>
          <button v-if="activeSvc.active !== 'active' && activeSvc.sub !== 'running'" type="button" @click="handleAction('start_service', activeSvc.name || activeSvc.unit)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:text-white hover:bg-emerald-950/80 flex items-center gap-2 cursor-pointer transition font-bold">Start</button>
          <button v-if="activeSvc.active === 'active' || activeSvc.sub === 'running'" type="button" @click="handleAction('reload_service', activeSvc.name || activeSvc.unit)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:text-white hover:bg-amber-950/80 flex items-center gap-2 cursor-pointer transition">Reload</button>
        </div>
        <div class="py-0.5">
          <button type="button" :disabled="isProtectedService(activeSvc.name || activeSvc.unit)" @click="handleAction('stop_service', activeSvc.name || activeSvc.unit)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 flex items-center gap-2 transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer" :title="isProtectedService(activeSvc.name || activeSvc.unit) ? 'Critical service is protected by guardrails' : 'Stop systemd service unit'">Stop</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'
import WorkspacePortsTable from './WorkspacePortsTable.vue'

const { t } = useI18n()

const props = defineProps({
  services: { type: Array, default: () => [] },
  ports: { type: Array, default: () => [] },
})

const emit = defineEmits(['restart-service', 'service-action'])

const mode = ref('services')
const search = ref('')
const statusFilter = ref('all')
const bootFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const openSvcId = ref(null)
const activeSvc = ref(null)
const dropdownStyle = ref({})

watch([search, statusFilter, bootFilter], () => { currentPage.value = 1 })

const runningCount = computed(() => (props.services || []).filter(s => s.sub === 'running' || s.active === 'active').length)
const failedCount = computed(() => (props.services || []).filter(s => s.sub === 'failed' || s.active === 'failed' || s.status === 'failed').length)

function svcBadgeClass(svc) {
  const st = (svc.sub || svc.status || svc.active || '').toLowerCase()
  if (st === 'running') return 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60'
  if (st === 'failed') return 'bg-rose-950/80 text-rose-300 border border-rose-700/60'
  if (st === 'exited') return 'bg-cyan-950/70 text-cyan-300 border border-cyan-700/50'
  return 'bg-gray-800 text-gray-400'
}

function closeDropdowns() { openSvcId.value = null; activeSvc.value = null }

function toggleSvcDropdown(svc, event) {
  const id = svc.name || svc.unit
  if (openSvcId.value === id) return closeDropdowns()
  openSvcId.value = id
  activeSvc.value = svc
  if (event?.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const isDropup = (window.innerHeight - rect.bottom < 170) && (rect.top > 170)
    const rightOffset = Math.max(8, window.innerWidth - rect.right)
    dropdownStyle.value = isDropup
      ? { position: 'fixed', bottom: `${Math.max(8, window.innerHeight - rect.top + 4)}px`, right: `${rightOffset}px`, zIndex: 100005, width: '144px' }
      : { position: 'fixed', top: `${Math.max(8, rect.bottom + 4)}px`, right: `${rightOffset}px`, zIndex: 100005, width: '144px' }
  }
}

onMounted(() => { window.addEventListener('click', closeDropdowns); window.addEventListener('scroll', closeDropdowns, true); window.addEventListener('resize', closeDropdowns) })
onUnmounted(() => { window.removeEventListener('click', closeDropdowns); window.removeEventListener('scroll', closeDropdowns, true); window.removeEventListener('resize', closeDropdowns) })

function isProtectedService(name) {
  const n = (name || '').toLowerCase()
  return ['agent_pantau', 'agent-pantau', 'sshd', 'ssh', 'systemd', 'pantau-server'].some(cs => n.includes(cs))
}

function handleAction(action, unit) {
  closeDropdowns()
  if (action === 'restart_service') emit('restart-service', unit)
  emit('service-action', { action, unit })
}

const filteredServices = computed(() => {
  return (props.services || []).filter(s => {
    const sub = (s.sub || s.status || s.active || '').toLowerCase()
    const act = (s.active || '').toLowerCase()
    const boot = (s.boot || '').toLowerCase()
    if (statusFilter.value === 'running' && sub !== 'running') return false
    if (statusFilter.value === 'exited' && sub !== 'exited') return false
    if (statusFilter.value === 'failed' && sub !== 'failed' && act !== 'failed') return false
    if (statusFilter.value === 'inactive' && !['inactive', 'stopped', 'dead'].includes(sub) && act !== 'inactive') return false
    if (bootFilter.value === 'enabled' && boot !== 'enabled') return false
    if (bootFilter.value === 'disabled' && boot !== 'disabled') return false
    if (bootFilter.value === 'static' && !['static', 'masked', 'indirect'].includes(boot)) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      if (!((s.name || s.unit || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q))) return false
    }
    return true
  })
})

const paginatedServices = computed(() => {
  if (pageSize.value === 'all') return filteredServices.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredServices.value.slice(start, start + limit)
})
</script>
