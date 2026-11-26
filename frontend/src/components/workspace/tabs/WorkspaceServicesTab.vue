<template>
  <div class="space-y-4 font-mono">
    <!-- Contextual Service History Panel -->
    <WorkspaceServiceHistoryPanel
      v-if="historyTarget"
      :server-id="serverId"
      :service-id="historyTarget.id"
      :service-name="historyTarget.service_name"
      @close="historyTarget = null"
    />

    <!-- Card 1: Monitored Services -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider">Monitored Services</h3>
          <p class="text-[11px] text-gray-400">Critical application daemons and ports tracked for uptime, connections, and latency</p>
        </div>
        <button
          v-if="canManage && !isViewer"
          type="button"
          :disabled="!isOnline"
          @click="showAddForm = !showAddForm"
          class="px-2.5 py-1 rounded text-[11px] font-bold bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-600/50 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
          :title="isOnline ? 'Add service or port to monitoring' : 'Server offline — action disabled'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Monitor Service</span>
        </button>
      </div>

      <!-- Inline Add Monitored Service Form -->
      <form v-if="showAddForm" @submit.prevent="submitAddService" class="grid grid-cols-1 sm:grid-cols-4 gap-2 p-3 rounded-lg bg-[#060a14] border border-cyan-800/50 text-xs">
        <input v-model="addForm.service_name" type="text" required placeholder="Service name (e.g. nginx)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 focus:border-cyan-500 outline-none" />
        <input v-model.number="addForm.port" type="number" min="1" max="65535" required placeholder="Port (e.g. 80)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 focus:border-cyan-500 outline-none" />
        <input v-model="addForm.process_name" type="text" placeholder="Process / unit (optional)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 focus:border-cyan-500 outline-none" />
        <div class="flex items-center gap-1.5">
          <button type="submit" :disabled="adding" class="flex-1 px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer disabled:opacity-50">Save</button>
          <button type="button" @click="showAddForm = false" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
        </div>
      </form>

      <div v-if="(monitoredServices || []).length === 0" class="py-5 text-center text-xs text-gray-500 italic">
        No monitored services registered yet. Add one above or from the Ports tab.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="bg-[#070c18] border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3">{{ t('ws_col_service_short') }}</th>
              <th class="py-2 px-3 text-center">{{ t('ws_col_port') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_process') }}</th>
              <th class="py-2 px-3 text-center">{{ t('col_status') }}</th>
              <th class="py-2 px-3 text-center">{{ t('ws_col_connections') }}</th>
              <th class="py-2 px-3 text-center">{{ t('ws_col_response_ms') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_info') }}</th>
              <th class="py-2 px-3 text-center">{{ t('ws_col_uptime_24h') }}</th>
              <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="ms in monitoredServices" :key="ms.id" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 font-bold">
                <button type="button" @click="historyTarget = ms" class="text-cyan-300 hover:text-cyan-200 hover:underline cursor-pointer inline-flex items-center gap-1" title="View service uptime & latency history">
                  <span>{{ ms.service_name }}</span>
                </button>
              </td>
              <td class="py-2 px-3 text-center text-gray-300">{{ ms.port || '-' }}</td>
              <td class="py-2 px-3 text-gray-400">{{ ms.process_name || '-' }}</td>
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold" :class="ms.status === 'up' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : (ms.is_ignored ? 'bg-gray-800 text-gray-400' : 'bg-rose-950 text-rose-300 border border-rose-800')">
                  {{ ms.status || 'unknown' }}
                </span>
              </td>
              <td class="py-2 px-3 text-center text-gray-300">{{ ms.connections ?? 0 }}</td>
              <td class="py-2 px-3 text-center text-gray-300">{{ ms.response_time_ms !== null && ms.response_time_ms !== undefined ? ms.response_time_ms : '-' }}</td>
              <td class="py-2 px-3 text-gray-400 truncate max-w-[200px]" :title="ms.health_message || ''">{{ ms.health_message || '-' }}</td>
              <td class="py-2 px-3 text-center font-semibold" :class="ms.uptime_24h >= 99 ? 'text-emerald-400' : (ms.uptime_24h >= 95 ? 'text-amber-400' : 'text-rose-400')">
                {{ ms.uptime_24h !== null && ms.uptime_24h !== undefined ? `${ms.uptime_24h}%` : '-' }}
              </td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="isViewer || !canManage"
                  type="button"
                  @click="historyTarget = ms"
                  class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 inline-flex items-center justify-center cursor-pointer"
                  :title="`View history for ${ms.service_name}`"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="openMenu('monitored', ms, $event)"
                  class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                  :title="`Actions for ${ms.service_name}`"
                >
                  <span>Actions</span>
                  <span class="text-[9px]">▾</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Card 2: Systemd Services (OS Daemons) -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2 flex-wrap">
          <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider">Systemd Services (OS Daemons)</h3>
          <button type="button" @click="statusFilter = 'all'" class="px-2 py-0.5 rounded border text-[11px] font-bold bg-cyan-950/50 text-cyan-300 border-cyan-800/60 cursor-pointer" title="Show all units">
            {{ (services || []).length }} units
          </button>
          <button type="button" @click="statusFilter = statusFilter === 'running' ? 'all' : 'running'" class="px-2 py-0.5 rounded border text-[11px] font-bold transition cursor-pointer" :class="statusFilter === 'running' ? 'bg-emerald-950 text-emerald-200 border-emerald-400' : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60'" title="Filter running services">
            {{ runningCount }} running
          </button>
          <button v-if="failedCount > 0" type="button" @click="statusFilter = statusFilter === 'failed' ? 'all' : 'failed'" class="px-2 py-0.5 rounded border text-[11px] font-bold transition cursor-pointer" :class="statusFilter === 'failed' ? 'bg-rose-950 text-rose-200 border-rose-400' : 'bg-rose-950/40 text-rose-300 border-rose-800/60'" title="Filter failed services">
            {{ failedCount }} failed
          </button>
        </div>

        <button
          type="button"
          :disabled="!isOnline"
          @click="$emit('refresh')"
          class="w-[28px] h-[28px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          :title="isOnline ? 'Refresh systemd units list' : 'Server offline — refresh disabled'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        </button>
      </div>

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

      <div class="overflow-x-auto max-h-[420px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3 cursor-pointer" @click="toggleSort('name')">Unit Name ↕</th>
              <th class="py-2 px-3 cursor-pointer" @click="toggleSort('status')">Status ↕</th>
              <th class="py-2 px-3 cursor-pointer" @click="toggleSort('boot')">Boot ↕</th>
              <th class="py-2 px-3">Memory</th>
              <th class="py-2 px-3">Description</th>
              <th class="py-2 px-3 text-center">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-if="paginatedServices.length === 0">
              <td colspan="6" class="py-8 text-center text-gray-500 italic">No service units match the selected filters.</td>
            </tr>
            <tr v-for="(svc, idx) in paginatedServices" :key="(svc.name || svc.unit) + idx" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 font-semibold text-gray-200 whitespace-nowrap">{{ svc.name || svc.unit }}</td>
              <td class="py-2 px-3 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold" :class="svcBadgeClass(svc)">
                  {{ svc.sub || svc.status || svc.active || 'unknown' }}
                </span>
              </td>
              <td class="py-2 px-3 text-gray-400 whitespace-nowrap text-[11px]">{{ svc.boot || '-' }}</td>
              <td class="py-2 px-3 text-gray-400 whitespace-nowrap text-[11px]">{{ svc.memory || '-' }}</td>
              <td class="py-2 px-3 text-gray-400 truncate max-w-xs" :title="svc.description || ''">{{ svc.description || '-' }}</td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="isViewer || !canManage"
                  type="button"
                  @click="$emit('view-logs', svc.name || svc.unit)"
                  class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 inline-flex items-center justify-center cursor-pointer"
                  :title="`View logs for ${svc.name || svc.unit}`"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="openMenu('systemd', svc, $event)"
                  class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                  :title="`Actions for ${svc.name || svc.unit}`"
                >
                  <span>Actions</span>
                  <span class="text-[9px]">▾</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredServices.length" unitLabel="services" :pageSizeOptions="[10, 25, 50, 100, 'all']" />
    </div>

    <!-- Floating Action Dropdown -->
    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <template v-if="menuKind === 'systemd'">
          <div class="py-0.5">
            <button type="button" :disabled="!isOnline" @click="execSvc('restart_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="isOnline ? 'Restart service' : 'Server offline'">Restart</button>
            <button type="button" :disabled="!isOnline || isUnitActive(menuTarget)" @click="execSvc('start_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="isUnitActive(menuTarget) ? 'Service is already running' : 'Start service'">Start</button>
            <button type="button" :disabled="!isOnline || !isUnitActive(menuTarget)" @click="execSvc('reload_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="!isUnitActive(menuTarget) ? 'Service is not running' : 'Reload configuration'">Reload</button>
            <button type="button" :disabled="!isOnline || !isUnitActive(menuTarget) || isProtected(menuTarget.name)" @click="execSvc('stop_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="isProtected(menuTarget.name) ? 'Protected critical system service' : (!isUnitActive(menuTarget) ? 'Service is already stopped' : 'Stop service')">Stop</button>
          </div>
          <div class="py-0.5">
            <button v-if="menuTarget.boot !== 'enabled'" type="button" :disabled="!isOnline || menuTarget.boot === 'static' || menuTarget.boot === 'masked'" @click="execSvc('enable_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-gray-200 hover:bg-gray-800/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Enable Autostart</button>
            <button v-else type="button" :disabled="!isOnline || isProtected(menuTarget.name)" @click="execSvc('disable_service', menuTarget.name)" class="w-full px-3 py-1.5 text-left text-gray-300 hover:bg-gray-800/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Disable Autostart</button>
            <button type="button" @click="viewLogs(menuTarget.name)" class="w-full px-3 py-1.5 text-left text-gray-200 hover:bg-gray-800/80 cursor-pointer">View Logs</button>
          </div>
        </template>

        <template v-else-if="menuKind === 'monitored'">
          <div class="py-0.5">
            <button type="button" :disabled="!isOnline" @click="execSvc('restart_service', menuTarget.process_name || menuTarget.service_name)" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Restart Service</button>
            <button type="button" :disabled="!isOnline || menuTarget.status === 'up'" @click="execSvc('start_service', menuTarget.process_name || menuTarget.service_name)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Start Service</button>
            <button type="button" :disabled="!isOnline || menuTarget.status !== 'up' || isProtected(menuTarget.service_name)" @click="execSvc('stop_service', menuTarget.process_name || menuTarget.service_name)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Stop Service</button>
          </div>
          <div class="py-0.5">
            <button type="button" @click="historyTarget = menuTarget; menuTarget = null" class="w-full px-3 py-1.5 text-left text-gray-200 hover:bg-gray-800/80 cursor-pointer">View History</button>
            <button type="button" @click="viewLogs(menuTarget.process_name || menuTarget.service_name)" class="w-full px-3 py-1.5 text-left text-gray-200 hover:bg-gray-800/80 cursor-pointer">View Logs</button>
            <button v-if="menuTarget.is_ignored" type="button" @click="toggleIgnore(menuTarget, false)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/60 cursor-pointer">Resume Monitoring</button>
            <button v-else type="button" :disabled="menuTarget.status === 'up'" @click="toggleIgnore(menuTarget, true)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Ignore Alert</button>
            <button type="button" @click="removeMonitored(menuTarget)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer">Remove</button>
          </div>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'
import WorkspaceServiceHistoryPanel from './WorkspaceServiceHistoryPanel.vue'

const { t } = useI18n()

const props = defineProps({
  serverId: { type: [Number, String], required: true },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
  canManage: { type: Boolean, default: true },
  services: { type: Array, default: () => [] },
  monitoredServices: { type: Array, default: () => [] },
})

const emit = defineEmits(['service-action', 'view-logs', 'refresh', 'monitored-updated'])

const search = ref('')
const statusFilter = ref('all')
const bootFilter = ref('all')
const sortKey = ref('name')
const sortAsc = ref(true)
const currentPage = ref(1)
const pageSize = ref(10)

const showAddForm = ref(false)
const adding = ref(false)
const addForm = ref({ service_name: '', port: '', process_name: '' })
const historyTarget = ref(null)

const menuTarget = ref(null)
const menuKind = ref('systemd')
const dropdownPos = ref({ top: 0, left: 0 })

watch([search, statusFilter, bootFilter], () => { currentPage.value = 1 })

const runningCount = computed(() => (props.services || []).filter(s => s.sub === 'running' || s.active === 'active' || s.status === 'up').length)
const failedCount = computed(() => (props.services || []).filter(s => s.sub === 'failed' || s.active === 'failed' || s.status === 'failed').length)

const filteredServices = computed(() => {
  return (props.services || []).filter(s => {
    const sub = (s.sub || '').toLowerCase()
    const act = (s.active || '').toLowerCase()
    const boot = (s.boot || '').toLowerCase()
    if (statusFilter.value === 'running' && sub !== 'running' && act !== 'active') return false
    if (statusFilter.value === 'exited' && sub !== 'exited') return false
    if (statusFilter.value === 'failed' && sub !== 'failed' && act !== 'failed') return false
    if (statusFilter.value === 'inactive' && (sub === 'running' || act === 'active')) return false
    if (bootFilter.value === 'enabled' && boot !== 'enabled') return false
    if (bootFilter.value === 'disabled' && boot !== 'disabled') return false
    if (bootFilter.value === 'static' && boot !== 'static' && boot !== 'masked') return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      if (!`${s.name || ''} ${s.description || ''}`.toLowerCase().includes(q)) return false
    }
    return true
  }).sort((a, b) => {
    const va = String(a[sortKey.value] || '').toLowerCase()
    const vb = String(b[sortKey.value] || '').toLowerCase()
    return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va)
  })
})

const paginatedServices = computed(() => {
  if (pageSize.value === 'all') return filteredServices.value
  const limit = parseInt(pageSize.value, 10) || 10
  return filteredServices.value.slice((currentPage.value - 1) * limit, currentPage.value * limit)
})

function toggleSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = true }
}

function isUnitActive(s) {
  return s.sub === 'running' || s.active === 'active' || s.status === 'up'
}

function isProtected(name) {
  const n = String(name || '').toLowerCase()
  return ['agent_pantau', 'agent-pantau', 'pantau-server', 'sshd', 'ssh', 'systemd'].some(p => n.includes(p))
}

function svcBadgeClass(s) {
  if (s.sub === 'failed' || s.active === 'failed') return 'bg-rose-950 text-rose-300 border border-rose-800'
  if (isUnitActive(s)) return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  return 'bg-gray-800 text-gray-400 border border-gray-700'
}

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: '175px',
}))

function openMenu(kind, item, event) {
  if (menuTarget.value === item && menuKind.value === kind) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 210),
    left: Math.max(8, Math.min(rect.right - 175, window.innerWidth - 183)),
  }
  menuKind.value = kind
  menuTarget.value = item
}

function execSvc(action, unit) {
  menuTarget.value = null
  emit('service-action', { action, unit })
}

function viewLogs(unit) {
  menuTarget.value = null
  emit('view-logs', unit)
}

async function submitAddService() {
  adding.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/services/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(addForm.value),
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      addForm.value = { service_name: '', port: '', process_name: '' }
      showAddForm.value = false
      emit('monitored-updated', { ok: true, message: data.message })
    } else {
      emit('monitored-updated', { ok: false, message: data.detail || 'Failed to add service' })
    }
  } finally {
    adding.value = false
  }
}

async function toggleIgnore(ms, ignore) {
  menuTarget.value = null
  const token = localStorage.getItem('pantau_token')
  const ep = ignore ? 'ignore' : 'unignore'
  const res = await fetch(`/api/servers/${props.serverId}/services/${ms.id}/${ep}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ duration: 'permanent' }),
  })
  const data = await res.json()
  emit('monitored-updated', { ok: res.ok && data.ok, message: data.message || data.detail })
}

async function removeMonitored(ms) {
  menuTarget.value = null
  const token = localStorage.getItem('pantau_token')
  const res = await fetch(`/api/servers/${props.serverId}/services/${ms.id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  const data = await res.json()
  emit('monitored-updated', { ok: res.ok && data.ok, message: data.message || data.detail })
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>
