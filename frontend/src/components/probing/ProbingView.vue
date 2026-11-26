<template>
  <div class="space-y-5 font-mono">
    <!-- Header -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between gap-3 flex-wrap shadow-lg">
      <div>
        <h2 class="text-sm font-extrabold text-cyan-300 tracking-wider uppercase">Synthetic Probing (HTTP / TCP / ICMP)</h2>
        <p class="text-[11px] text-gray-400 mt-0.5">Agentless endpoint availability, latency, and TLS certificate monitoring.</p>
      </div>
      <div class="flex items-center gap-2">
        <button v-if="canManage" @click="openAddModal" class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition cursor-pointer">
          + Add Probe
        </button>
        <button @click="fetchProbes" class="w-[26px] h-[26px] flex items-center justify-center rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 cursor-pointer" title="Refresh Probes">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
        </button>
      </div>
    </div>

    <!-- KPI Strip -->
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3">
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-gray-400">Total Probes</div><div class="text-2xl font-extrabold text-gray-100 mt-1">{{ summary.total }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-emerald-400">Operational (Up)</div><div class="text-2xl font-extrabold text-emerald-300 mt-1">{{ summary.up }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-amber-400">Degraded</div><div class="text-2xl font-extrabold text-amber-300 mt-1">{{ summary.degraded }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-rose-400">Down</div><div class="text-2xl font-extrabold text-rose-300 mt-1">{{ summary.down }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-cyan-400">Avg Latency</div><div class="text-2xl font-extrabold text-cyan-300 mt-1">{{ summary.avg_latency_ms !== null ? `${summary.avg_latency_ms} ms` : '-' }}</div></div>
    </div>

    <!-- Filters & Table -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-xl">
      <div class="p-3 border-b border-gray-800 flex items-center gap-2 flex-wrap bg-[#070c18]/70 text-xs">
        <select v-model="filterType" @change="fetchProbes" class="bg-[#0b1324] border border-gray-700 rounded px-2.5 py-1 text-gray-200">
          <option value="all">All Protocols</option>
          <option value="https">HTTPS</option>
          <option value="http">HTTP</option>
          <option value="tcp">TCP</option>
          <option value="icmp">ICMP</option>
        </select>
        <select v-model="filterStatus" @change="fetchProbes" class="bg-[#0b1324] border border-gray-700 rounded px-2.5 py-1 text-gray-200">
          <option value="all">All Statuses</option>
          <option value="up">Up</option>
          <option value="degraded">Degraded</option>
          <option value="down">Down</option>
          <option value="paused">Paused</option>
        </select>
        <input v-model="search" @input="fetchProbes" placeholder="Search probe name or target..." class="bg-[#0b1324] border border-gray-700 rounded px-2.5 py-1 text-gray-200 flex-1 min-w-[180px]" />
      </div>

      <div v-if="probes.length === 0" class="p-8 text-center text-xs text-gray-400">
        No synthetic probes configured yet.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="border-b border-cyan-500/20 text-gray-400 bg-[#070c18]/80 font-bold">
            <tr>
              <th class="py-2.5 px-3">{{ t('th_status') }}</th>
              <th class="py-2.5 px-3">{{ t('th_name') }}</th>
              <th class="py-2.5 px-3">{{ t('th_type') }}</th>
              <th class="py-2.5 px-3">{{ t('th_target') }}</th>
              <th class="py-2.5 px-3">{{ t('th_latency') }}</th>
              <th class="py-2.5 px-3">{{ t('th_uptime_24h') }}</th>
              <th class="py-2.5 px-3">{{ t('th_last_checked') }}</th>
              <th v-if="canManage" class="py-2.5 px-3 text-right">{{ t('th_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr v-for="p in paginatedProbes" :key="p.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-3">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border" :class="statusClass(p.status)">{{ p.status }}</span>
              </td>
              <td class="py-2.5 px-3 font-bold text-gray-100">{{ p.name }}</td>
              <td class="py-2.5 px-3 uppercase text-cyan-300">{{ p.probe_type }}</td>
              <td class="py-2.5 px-3 text-gray-300 max-w-xs truncate" :title="p.last_error || p.target">{{ p.target }}{{ p.port ? `:${p.port}` : '' }}</td>
              <td class="py-2.5 px-3 text-gray-300">{{ p.last_latency_ms !== null ? `${p.last_latency_ms} ms` : '-' }}</td>
              <td class="py-2.5 px-3 text-emerald-300 font-bold">{{ p.uptime_24h }}%</td>
              <td class="py-2.5 px-3 text-gray-400" :title="p.last_checked_at || ''">{{ formatRelativeTime(p.last_checked_at) }}</td>
              <td v-if="canManage" class="py-2.5 px-3 text-right">
                <button @click="toggleDropdown(p, $event)" class="h-6 min-w-[58px] px-2 rounded bg-[#0b1324] hover:bg-cyan-950 text-cyan-300 border border-cyan-500/40 text-[11px] font-bold cursor-pointer">
                  Actions ▾
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="probes.length" unitLabel="probes" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Floating Dropdown (> 2 Actions) -->
    <Teleport to="body">
      <div v-if="activeProbe" class="fixed inset-0 z-[9998]" @click="activeProbe = null">
        <div :style="dropdownStyle" class="fixed z-[9999] w-40 bg-[#080d19] border border-cyan-500/50 rounded-lg shadow-2xl py-1 text-xs font-mono" @click.stop>
          <button @click="testNow(activeProbe); activeProbe = null" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/60 text-cyan-300 cursor-pointer">Test Now</button>
          <button @click="toggleProbe(activeProbe); activeProbe = null" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/60 text-amber-300 cursor-pointer">{{ activeProbe.is_active ? 'Pause' : 'Resume' }}</button>
          <button @click="openEditModal(activeProbe); activeProbe = null" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/60 text-gray-200 cursor-pointer">Edit</button>
          <button @click="deleteProbe(activeProbe); activeProbe = null" class="w-full text-left px-3 py-1.5 hover:bg-rose-950/60 text-rose-400 cursor-pointer">Delete</button>
        </div>
      </div>
    </Teleport>

    <ProbeModal :is-open="showModal" :editing-probe="editingProbe" :servers="servers" @close="showModal = false" @saved="fetchProbes" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '../../i18n'
import { apiFetch } from '../../utils/api'
import { formatRelativeTime } from '../../utils/formatters'
import { useToast } from '../../utils/useToast'
import NocTablePagination from '../common/NocTablePagination.vue'
import ProbeModal from './ProbeModal.vue'

const { t } = useI18n()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null },
})
const toast = useToast()
const probes = ref([])
const summary = ref({ total: 0, up: 0, down: 0, degraded: 0, paused: 0, avg_latency_ms: null })
const filterType = ref('all')
const filterStatus = ref('all')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const showModal = ref(false)
const editingProbe = ref(null)
const activeProbe = ref(null)
const dropdownStyle = ref({})

const canManage = computed(() => Boolean(props.currentUser?.is_master_admin || props.currentUser?.permissions?.can_probing))
const paginatedProbes = computed(() => {
  if (pageSize.value === 'all') return probes.value
  const lim = parseInt(pageSize.value, 10) || 10
  return probes.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})

function statusClass(st) {
  if (st === 'up') return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60'
  if (st === 'degraded') return 'bg-amber-950/80 text-amber-300 border-amber-600/60'
  if (st === 'down') return 'bg-rose-950/80 text-rose-300 border-rose-600/60'
  return 'bg-gray-800/80 text-gray-400 border-gray-700'
}

function toggleDropdown(p, ev) {
  const rect = ev.currentTarget.getBoundingClientRect()
  dropdownStyle.value = { top: `${rect.bottom + 4}px`, left: `${Math.max(8, rect.right - 160)}px` }
  activeProbe.value = p
}

async function fetchProbes() {
  const qs = new URLSearchParams({ probe_type: filterType.value, status_filter: filterStatus.value, search: search.value })
  const res = await apiFetch(`/api/probes?${qs}`)
  if (res.ok) {
    const data = await res.json()
    probes.value = data.probes || []
    summary.value = data.summary || summary.value
  }
}

function openAddModal() { editingProbe.value = null; showModal.value = true }
function openEditModal(p) { editingProbe.value = p; showModal.value = true }

async function testNow(p) {
  toast.info(`Testing ${p.name}...`)
  const res = await apiFetch(`/api/probes/${p.id}/test`, { method: 'POST' })
  const data = await res.json()
  if (res.ok) {
    toast.success(`${p.name}: ${data.result?.status?.toUpperCase()} (${data.result?.latency_ms ?? '-'} ms)`)
    fetchProbes()
  } else {
    toast.error(data.detail || 'Probe test failed')
  }
}

async function toggleProbe(p) {
  const res = await apiFetch(`/api/probes/${p.id}/toggle`, { method: 'POST' })
  if (res.ok) { toast.success((await res.json()).message); fetchProbes() }
}

async function deleteProbe(p) {
  const res = await apiFetch(`/api/probes/${p.id}`, { method: 'DELETE' })
  if (res.ok) { toast.success((await res.json()).message); fetchProbes() }
}

onMounted(fetchProbes)
</script>
