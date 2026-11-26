<template>
  <div class="hud-tactical-card rounded-xl p-4 space-y-3 font-mono">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div>
        <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider">Listening Ports &amp; Sockets</h3>
        <p class="text-[11px] text-gray-400">Active TCP/UDP listening sockets reported by kernel ss -tulpn</p>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          @click="accessFilter = ''"
          class="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-950/60 text-cyan-300 border border-cyan-800/60 cursor-pointer"
          title="Show all listening sockets"
        >
          {{ (ports || []).length }} active sockets
        </button>
        <button
          v-if="publicCount > 0"
          type="button"
          @click="accessFilter = accessFilter === 'public' ? '' : 'public'"
          class="px-2 py-0.5 rounded text-[11px] font-bold border transition cursor-pointer"
          :class="accessFilter === 'public' ? 'bg-rose-950 text-rose-200 border-rose-400' : 'bg-rose-950/40 text-rose-300 border-rose-800/60'"
          title="Filter public exposed ports (click again to reset)"
        >
          {{ publicCount }} public
        </button>
      </div>
    </div>

    <NocFilterPanel
      :has-active-filters="Boolean(protoFilter || accessFilter || search.trim())"
      :summary-text="`${filteredPorts.length} of ${(ports || []).length} sockets`"
      compact
      @reset="protoFilter = ''; accessFilter = ''; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="port-proto-filter">{{ t('flt_protocol') }}</label>
          <select id="port-proto-filter" v-model="protoFilter" class="noc-filter-select">
            <option value="">{{ t('flt_all_protocols') }}</option>
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
        </div>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="port-access-filter">{{ t('flt_access') }}</label>
          <select id="port-access-filter" v-model="accessFilter" class="noc-filter-select">
            <option value="">{{ t('flt_all_access') }}</option>
            <option value="public">{{ t('flt_access_public') }}</option>
            <option value="local">{{ t('flt_access_local') }}</option>
          </select>
        </div>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="port-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="port-search-input" v-model="search" type="search" placeholder="Search port, bind IP, process, PID..." />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="paginatedPorts.length === 0" class="text-xs text-gray-400 py-8 text-center">
      No listening sockets match the selected criteria.
    </div>
    <div v-else class="overflow-x-auto max-h-[460px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
          <tr class="text-gray-400 uppercase font-bold tracking-wider">
            <th class="py-2 px-3 cursor-pointer" @click="toggleSort('proto')">{{ t('ws_col_proto') || 'Proto' }} ↕</th>
            <th class="py-2 px-3 cursor-pointer" @click="toggleSort('port')">{{ t('ws_col_port') || 'Port' }} ↕</th>
            <th class="py-2 px-3">{{ t('ws_col_bind') }}</th>
            <th class="py-2 px-3 text-center cursor-pointer" @click="toggleSort('access')">{{ t('ws_col_class') }} ↕</th>
            <th class="py-2 px-3">{{ t('ws_col_service') }}</th>
            <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(pt, idx) in paginatedPorts" :key="`${pt.proto}-${pt.port}-${idx}`" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 uppercase font-bold" :class="pt.proto === 'udp' ? 'text-amber-300' : 'text-cyan-300'">{{ pt.proto || 'tcp' }}</td>
            <td class="py-2 px-3 font-bold text-gray-100">{{ pt.port }}</td>
            <td class="py-2 px-3 text-gray-400 font-semibold">{{ pt.ip || pt.bind || pt.address || '0.0.0.0' }}</td>
            <td class="py-2 px-3 text-center">
              <span
                class="px-2 py-0.5 rounded text-[10px] font-bold"
                :class="isPublicPort(pt) ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'"
                :title="isPublicPort(pt) ? 'Exposed to external network interfaces' : 'Bound to loopback interface only'"
              >
                {{ isPublicPort(pt) ? 'PUBLIC' : 'LOCAL' }}
              </span>
            </td>
            <td class="py-2 px-3 text-gray-200">{{ pt.proc || pt.service || pt.program || pt.process || '-' }}</td>
            <td class="py-2 px-3 text-center">
              <button
                v-if="isViewer"
                type="button"
                disabled
                class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 border border-gray-700 text-gray-500 opacity-40 cursor-not-allowed inline-flex items-center justify-center"
                title="Read-only role: port actions are disabled"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button
                v-else
                type="button"
                @click.stop="openMenu(pt, $event)"
                class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                :title="`Port ${pt.port}/${pt.proto || 'tcp'} actions`"
              >
                <span>Actions</span>
                <span class="text-[9px]">▾</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination
      v-model:page="currentPage"
      v-model:pageSize="pageSize"
      :total="filteredPorts.length"
      unitLabel="ports"
      :pageSizeOptions="[10, 25, 50, 100, 'all']"
    />

    <!-- Floating Port Actions Dropdown -->
    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div v-if="isMgmtPort(menuTarget)" class="px-3 py-2 text-[11px] text-gray-400 flex items-center gap-1.5" :title="`Management port ${menuTarget.port} is protected by Pantau Server guardrails.`">
          <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <span>Protected Management Port</span>
        </div>
        <template v-else>
          <div class="py-0.5">
            <button
              v-if="canServices"
              type="button"
              :disabled="!isOnline || isPortMonitored(menuTarget)"
              @click="monitorPort(menuTarget)"
              class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="!isOnline ? 'Server offline' : (isPortMonitored(menuTarget) ? `Port ${menuTarget.port} is already registered in Monitored Services` : `Register port ${menuTarget.port} to Monitored Services`)"
            >
              {{ isPortMonitored(menuTarget) ? 'Already Monitored' : 'Monitor as Service' }}
            </button>
            <button
              v-if="canProcesses && menuTarget.pid"
              type="button"
              :disabled="!isOnline || isCriticalProc(menuTarget)"
              @click="terminatePid(menuTarget)"
              class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="isCriticalProc(menuTarget) ? 'Critical system process is protected by guardrails' : `Terminate PID ${menuTarget.pid}`"
            >
              Terminate PID ({{ menuTarget.pid }})
            </button>
          </div>
          <div v-if="canFirewall" class="py-0.5">
            <button
              v-if="isPublicPort(menuTarget)"
              type="button"
              :disabled="!isOnline"
              @click="toggleFirewallPort(menuTarget, 'deny')"
              class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="`Block public port ${menuTarget.port}/${menuTarget.proto || 'tcp'} via firewall`"
            >
              Block Port (Firewall)
            </button>
            <button
              v-else
              type="button"
              :disabled="!isOnline"
              @click="toggleFirewallPort(menuTarget, 'allow')"
              class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="`Allow port ${menuTarget.port}/${menuTarget.proto || 'tcp'} via firewall`"
            >
              Allow Port (Firewall)
            </button>
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

const { t } = useI18n()

const props = defineProps({
  ports: { type: Array, default: () => [] },
  monitoredServices: { type: Array, default: () => [] },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
  canServices: { type: Boolean, default: false },
  canProcesses: { type: Boolean, default: false },
  canFirewall: { type: Boolean, default: false },
})

const emit = defineEmits(['monitor-port', 'kill-process', 'firewall-port'])

const protoFilter = ref('')
const accessFilter = ref('')
const search = ref('')
const sortKey = ref('port')
const sortAsc = ref(true)
const currentPage = ref(1)
const pageSize = ref(10)
const menuTarget = ref(null)
const dropdownPos = ref({ top: 0, left: 0 })

watch([protoFilter, accessFilter, search], () => { currentPage.value = 1 })

const publicCount = computed(() => (props.ports || []).filter(isPublicPort).length)

function isPortMonitored(pt) {
  const p = Number(pt?.port)
  return Boolean(p && (props.monitoredServices || []).some(ms => Number(ms.port) === p))
}

function toggleSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = true }
}

function isPublicPort(pt) {
  if (typeof pt.is_public === 'boolean') return pt.is_public
  const ip = String(pt.ip || pt.bind || pt.address || '')
  return !(pt.is_loopback || ip.startsWith('127.') || ip === '::1')
}

function isMgmtPort(pt) {
  const p = Number(pt.port)
  return p === 22 || p === 8400
}

function isCriticalProc(pt) {
  const pid = Number(pt.pid || 0)
  const pname = String(pt.pname || pt.proc || '').toLowerCase()
  return pid <= 1 || ['sshd', 'ssh', 'systemd', 'pantau-server', 'agent_pantau', 'agent-pantau'].some(c => pname.includes(c))
}

const filteredPorts = computed(() => {
  return (props.ports || []).filter(pt => {
    if (protoFilter.value && (pt.proto || '').toLowerCase() !== protoFilter.value) return false
    if (accessFilter.value === 'public' && !isPublicPort(pt)) return false
    if (accessFilter.value === 'local' && isPublicPort(pt)) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = `${pt.proto || ''} ${pt.port || ''} ${pt.ip || pt.bind || ''} ${pt.proc || pt.service || pt.process || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  }).sort((a, b) => {
    if (sortKey.value === 'port') {
      return sortAsc.value ? (Number(a.port) - Number(b.port)) : (Number(b.port) - Number(a.port))
    }
    if (sortKey.value === 'access') {
      const va = isPublicPort(a) ? 0 : 1
      const vb = isPublicPort(b) ? 0 : 1
      return sortAsc.value ? (va - vb) : (vb - va)
    }
    const va = String(a[sortKey.value] || '').toLowerCase()
    const vb = String(b[sortKey.value] || '').toLowerCase()
    return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va)
  })
})

const paginatedPorts = computed(() => {
  if (pageSize.value === 'all') return filteredPorts.value
  const limit = parseInt(pageSize.value, 10) || 10
  return filteredPorts.value.slice((currentPage.value - 1) * limit, currentPage.value * limit)
})

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: '205px',
}))

function openMenu(pt, event) {
  if (menuTarget.value === pt) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 160),
    left: Math.max(8, Math.min(rect.right - 205, window.innerWidth - 213)),
  }
  menuTarget.value = pt
}

function monitorPort(pt) {
  menuTarget.value = null
  const pname = String(pt.pname || pt.proc || `port-${pt.port}`).split(' ')[0]
  emit('monitor-port', { service_name: pname, port: Number(pt.port), process_name: pname })
}

function terminatePid(pt) {
  menuTarget.value = null
  emit('kill-process', { pid: Number(pt.pid), signal: 'SIGTERM', pname: pt.pname || pt.proc || '' })
}

function toggleFirewallPort(pt, rule) {
  menuTarget.value = null
  emit('firewall-port', { port: `${pt.port}/${(pt.proto || 'tcp').toLowerCase()}`, rule })
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>
