<template>
  <div class="space-y-4">
    <!-- KPI Strip -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 font-mono">
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-cyan-400">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Total Endpoints</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">{{ summary.total || 0 }}</div>
      </div>
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-emerald-400">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Healthy (UP)</div>
        <div class="text-xl font-black text-emerald-400 mt-0.5">{{ summary.up || 0 }}</div>
      </div>
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-rose-500">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Down</div>
        <div class="text-xl font-black text-rose-400 mt-0.5">{{ summary.down || 0 }}</div>
      </div>
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-amber-400">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Degraded</div>
        <div class="text-xl font-black text-amber-400 mt-0.5">{{ summary.degraded || 0 }}</div>
      </div>
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-purple-400">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Avg Latency</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">{{ summary.avg_latency_ms !== null && summary.avg_latency_ms !== undefined ? `${summary.avg_latency_ms} ms` : '—' }}</div>
      </div>
      <div class="hud-tactical-card p-3 rounded-lg border-l-2 border-l-sky-400">
        <div class="text-[11px] text-gray-400 uppercase font-bold">Paused</div>
        <div class="text-xl font-black text-gray-400 mt-0.5">{{ summary.paused || 0 }}</div>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="hud-tactical-card p-3 rounded-xl flex flex-wrap items-center justify-between gap-2.5 text-xs font-mono">
      <div class="flex flex-wrap items-center gap-2 flex-1">
        <input v-model="searchQuery" type="search" placeholder="Search endpoint, URL, IP..." class="bg-[#060a14] border border-gray-700 focus:border-cyan-500 rounded px-2.5 py-1.5 text-gray-100 w-56 outline-none" />
        <select v-model="typeFilter" class="bg-[#060a14] border border-gray-700 rounded px-2.5 py-1.5 text-gray-200 outline-none cursor-pointer">
          <option value="all">All Protocols</option>
          <option value="web">Web (HTTP / HTTPS)</option>
          <option value="icmp">Network Ping (ICMP)</option>
          <option value="tcp">TCP Port</option>
        </select>
        <select v-model="statusFilter" class="bg-[#060a14] border border-gray-700 rounded px-2.5 py-1.5 text-gray-200 outline-none cursor-pointer">
          <option value="all">All Statuses</option>
          <option value="up">UP</option>
          <option value="down">DOWN</option>
          <option value="degraded">Degraded</option>
          <option value="paused">Paused</option>
        </select>
        <button v-if="searchQuery || typeFilter !== 'all' || statusFilter !== 'all'" type="button" @click="resetFilters" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-amber-300 font-bold cursor-pointer">Reset</button>
      </div>
      <button type="button" @click="fetchProbes" class="px-2.5 py-1.5 rounded bg-[#060a14] border border-gray-700 hover:border-cyan-500 text-gray-300 hover:text-cyan-300 cursor-pointer" title="Refresh Endpoints">
        Refresh
      </button>
    </div>

    <!-- Endpoints Table -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl mb-8">
      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 font-bold tracking-wider select-none">
              <th class="py-2 pl-4 pr-3 w-24 text-center">{{ t('th_status') }}</th>
              <th class="py-2 px-3 min-w-[200px]">{{ t('th_endpoint') }}</th>
              <th class="py-2 px-3 min-w-[130px]">{{ t('th_linked_asset') }}</th>
              <th class="py-2 px-3 text-right">{{ t('th_latency') }}</th>
              <th class="py-2 px-3 text-center">{{ t('th_uptime_24h_30d') }}</th>
              <th class="py-2 px-3 text-center">{{ t('th_interval') }}</th>
              <th class="py-2 pl-3 pr-4 text-right w-28">{{ t('th_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr v-for="p in paginatedProbes" :key="p.id" class="hover:bg-cyan-950/20 transition-colors">
              <td class="py-2 pl-4 pr-3 text-center whitespace-nowrap">
                <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10.5px] font-bold uppercase" :class="statusBadgeClass(p.status)">
                  {{ p.status }}
                </span>
              </td>
              <td class="py-2 px-3">
                <div class="flex items-center gap-2">
                  <span class="px-1.5 py-0.5 rounded text-[9.5px] font-bold uppercase bg-cyan-950/70 text-cyan-300 border border-cyan-700/50">{{ p.probe_type }}</span>
                  <span class="font-bold text-gray-100">{{ p.name }}</span>
                </div>
                <div class="text-[11px] text-gray-400 mt-0.5 truncate max-w-md" :title="p.last_error || p.target">
                  {{ p.target }}{{ p.port ? `:${p.port}` : '' }}
                  <span v-if="p.last_error && p.status !== 'up'" class="text-rose-300 ml-1">— {{ p.last_error }}</span>
                </div>
              </td>
              <td class="py-2 px-3 text-gray-300 whitespace-nowrap">{{ p.server_hostname || 'Standalone' }}</td>
              <td class="py-2 px-3 text-right text-gray-200 whitespace-nowrap">{{ p.last_latency_ms !== null ? `${p.last_latency_ms} ms` : '—' }}</td>
              <td class="py-2 px-3 text-center text-gray-300 whitespace-nowrap">{{ p.uptime_24h }}% / {{ p.uptime_30d }}%</td>
              <td class="py-2 px-3 text-center text-gray-400 whitespace-nowrap">{{ p.interval_seconds }}s</td>
              <td class="py-2 pl-3 pr-4 text-right whitespace-nowrap">
                <button
                  v-if="!canManage"
                  @click="historyTarget = p"
                  class="w-[26px] h-[26px] min-w-[26px] inline-flex items-center justify-center rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700/80 cursor-pointer"
                  title="View Check History"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="toggleDropdown(p, $event)"
                  class="h-6 min-w-[58px] px-2 py-0.5 rounded bg-[#0b1324] hover:bg-cyan-950/60 text-cyan-300 border border-gray-700 hover:border-cyan-500 font-bold text-[11px] transition cursor-pointer inline-flex items-center justify-between gap-1 select-none"
                >
                  <span>Actions</span>
                  <svg class="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
              </td>
            </tr>
            <tr v-if="!loading && probes.length === 0">
              <td colspan="7" class="py-12 px-4 text-center text-gray-400">
                No endpoints configured yet. Click "+ Add Endpoint" to monitor HTTP/HTTPS, ICMP Ping, or TCP Port targets.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="probes.length" unitLabel="endpoints" />
    </div>

    <Teleport to="body">
      <div v-if="openMenuProbe" @click.stop :style="menuStyle" class="rounded-md bg-[#0a0f1d] border border-gray-700 shadow-2xl py-1 z-[100005] text-xs font-mono">
        <button @click="testNow(openMenuProbe); closeDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 cursor-pointer">Test Now</button>
        <button @click="historyTarget = openMenuProbe; closeDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-200 cursor-pointer border-t border-gray-800/60">View History</button>
        <button @click="toggleProbe(openMenuProbe); closeDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-amber-300 cursor-pointer border-t border-gray-800/60">{{ openMenuProbe.is_active ? 'Pause Monitoring' : 'Resume Monitoring' }}</button>
        <button @click="$emit('edit-probe', openMenuProbe); closeDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-200 cursor-pointer border-t border-gray-800/60">Edit</button>
        <button @click="deleteProbe(openMenuProbe); closeDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-rose-950/50 text-rose-300 cursor-pointer border-t border-gray-800/60">Delete</button>
      </div>
    </Teleport>

    <EndpointHistoryModal :probe="historyTarget" @close="historyTarget = null" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import { apiFetch } from '../../utils/api'
import { useToast, confirmAction } from '../../utils/useToast'
import NocTablePagination from '../common/NocTablePagination.vue'
import EndpointHistoryModal from './modals/EndpointHistoryModal.vue'

const props = defineProps({
  canManage: { type: Boolean, default: false },
})
const emit = defineEmits(['edit-probe', 'count-updated'])
const { t } = useI18n()
const toast = useToast()

const probes = ref([])
const summary = ref({ total: 0, up: 0, down: 0, degraded: 0, paused: 0, avg_latency_ms: null })
const loading = ref(false)
const searchQuery = ref('')
const typeFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const historyTarget = ref(null)
const openMenuProbe = ref(null)
const menuStyle = ref({})

const paginatedProbes = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return probes.value.slice(start, start + pageSize.value)
})

function statusBadgeClass(st) {
  if (st === 'up') return 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60'
  if (st === 'down') return 'bg-rose-950/80 text-rose-300 border border-rose-700/60'
  if (st === 'degraded') return 'bg-amber-950/80 text-amber-300 border border-amber-700/60'
  return 'bg-slate-800 text-slate-400 border border-slate-700'
}

async function fetchProbes() {
  loading.value = true
  try {
    const qs = new URLSearchParams()
    if (typeFilter.value !== 'all') qs.set('probe_type', typeFilter.value)
    if (statusFilter.value !== 'all') qs.set('status_filter', statusFilter.value)
    if (searchQuery.value.trim()) qs.set('search', searchQuery.value.trim())
    const res = await apiFetch(`/api/probes?${qs.toString()}`)
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to load endpoints')
    probes.value = data.probes || []
    summary.value = data.summary || summary.value
    emit('count-updated', summary.value.total || 0)
  } catch (err) {
    toast.error(err.message)
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  searchQuery.value = ''
  typeFilter.value = 'all'
  statusFilter.value = 'all'
}

async function testNow(p) {
  try {
    const res = await apiFetch(`/api/probes/${p.id}/test`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Test failed')
    const r = data.result || {}
    toast.success(`${p.name}: ${(r.status || 'done').toUpperCase()} (${r.latency_ms ?? '-'} ms)`)
    await fetchProbes()
  } catch (err) {
    toast.error(err.message)
  }
}

async function toggleProbe(p) {
  try {
    const res = await apiFetch(`/api/probes/${p.id}/toggle`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Toggle failed')
    toast.success(data.message)
    await fetchProbes()
  } catch (err) {
    toast.error(err.message)
  }
}

async function deleteProbe(p) {
  const ok = await confirmAction(`Delete endpoint "${p.name}" and its check history?`)
  if (!ok) return
  try {
    const res = await apiFetch(`/api/probes/${p.id}`, { method: 'DELETE' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Delete failed')
    toast.success(data.message)
    await fetchProbes()
  } catch (err) {
    toast.error(err.message)
  }
}

function toggleDropdown(p, ev) {
  if (openMenuProbe.value?.id === p.id) {
    openMenuProbe.value = null
    return
  }
  const rect = ev.currentTarget.getBoundingClientRect()
  menuStyle.value = { position: 'fixed', top: `${rect.bottom + 4}px`, right: `${window.innerWidth - rect.right}px`, minWidth: '165px' }
  openMenuProbe.value = p
}

function closeDropdown() { openMenuProbe.value = null }

watch([typeFilter, statusFilter, searchQuery], () => { currentPage.value = 1; fetchProbes() })
onMounted(() => { fetchProbes(); window.addEventListener('click', closeDropdown) })
onUnmounted(() => { window.removeEventListener('click', closeDropdown) })
defineExpose({ fetchProbes })
</script>
