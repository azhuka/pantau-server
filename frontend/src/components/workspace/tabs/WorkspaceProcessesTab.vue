<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">{{ t('ws_procs_title') }}</h3>
        <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
          {{ filteredProcesses.length }} processes
        </span>
      </div>
      <button
        type="button"
        :disabled="!isOnline"
        @click="$emit('refresh')"
        class="w-[28px] h-[28px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        :title="isOnline ? 'Refresh running processes snapshot' : 'Server offline — refresh disabled'"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
    </div>

    <NocFilterPanel
      :has-active-filters="Boolean(search.trim())"
      :summary-text="`${filteredProcesses.length} of ${(processes || []).length} processes`"
      compact
      @reset="search = ''"
    >
      <template #fields>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="proc-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="proc-search-input" v-model="search" type="search" :placeholder="t('ws_procs_search')" />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div class="overflow-x-auto max-h-[500px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
          <tr class="text-gray-400 uppercase font-bold tracking-wider">
            <th class="py-2 px-3 cursor-pointer" @click="toggleSort('pid')">{{ t('ws_col_pid') || 'PID' }} ↕</th>
            <th class="py-2 px-3 cursor-pointer" @click="toggleSort('user')">{{ t('ws_col_user') }} ↕</th>
            <th class="py-2 px-3 cursor-pointer" @click="toggleSort('cmd')">{{ t('ws_col_command') }} ↕</th>
            <th class="py-2 px-3 text-center cursor-pointer" @click="toggleSort('state')">{{ t('col_status') }} ↕</th>
            <th class="py-2 px-3 text-right cursor-pointer" @click="toggleSort('cpu')">{{ t('col_cpu_pct') || 'CPU %' }} ↕</th>
            <th class="py-2 px-3 text-right cursor-pointer" @click="toggleSort('mem')">{{ t('col_ram_pct') || 'RAM %' }} ↕</th>
            <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-if="paginatedProcesses.length === 0">
            <td colspan="7" class="py-8 text-center text-gray-500 italic">No processes match the search filter.</td>
          </tr>
          <tr v-for="(p, idx) in paginatedProcesses" :key="`${p.pid}-${idx}`" class="hover:bg-cyan-950/20" :class="{ 'bg-amber-950/15': isPaused(p) }">
            <td class="py-2 px-3 text-cyan-400 font-bold whitespace-nowrap">{{ p.pid }}</td>
            <td class="py-2 px-3 whitespace-nowrap">
              <span class="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-200 border border-cyan-800/50 text-[10px]">{{ p.user || '-' }}</span>
            </td>
            <td class="py-2 px-3 text-gray-200 truncate max-w-sm cursor-help" :title="p.cmd || p.command">
              {{ p.cmd || p.command }}
            </td>
            <td class="py-2 px-3 text-center whitespace-nowrap">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="stateBadgeClass(p)" :title="stateTitle(p)">
                {{ stateLabel(p) }}
              </span>
            </td>
            <td class="py-2 px-3 text-right font-semibold whitespace-nowrap" :class="metricColor(p.cpu || p.cpu_percent || 0)">
              {{ Number(p.cpu || p.cpu_percent || 0).toFixed(1) }}%
            </td>
            <td class="py-2 px-3 text-right font-semibold whitespace-nowrap" :class="metricColor(p.mem || p.mem_percent || 0)">
              {{ Number(p.mem || p.mem_percent || 0).toFixed(1) }}%
            </td>
            <td class="py-2 px-3 text-center whitespace-nowrap">
              <button
                v-if="isViewer"
                type="button"
                disabled
                class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 border border-gray-700 text-gray-500 opacity-40 cursor-not-allowed inline-flex items-center justify-center"
                title="Read-only role: process actions are disabled"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button
                v-else
                type="button"
                @click.stop="toggleProcDropdown(p, $event)"
                class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                :title="`Process PID ${p.pid} actions`"
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
      :total="filteredProcesses.length"
      unitLabel="processes"
      :pageSizeOptions="[10, 25, 50, 100, 'all']"
    />

    <!-- Floating Process Action Dropdown Menu -->
    <Teleport to="body">
      <div
        v-if="openProcId && activeProc"
        @click.stop
        :style="dropdownStyle"
        class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none"
      >
        <div v-if="isProtected(activeProc)" class="px-3 py-2 text-[11px] text-gray-400 flex items-center gap-1.5" title="Critical system process is protected by Pantau Server guardrails.">
          <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <span>Protected System Process</span>
        </div>
        <template v-else>
          <div class="py-0.5">
            <button type="button" :disabled="!isOnline" @click="sendSignal(activeProc.pid, 'SIGTERM', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed font-bold" title="Graceful termination (SIGTERM 15)">SIGTERM (Terminate)</button>
            <button type="button" :disabled="!isOnline" @click="sendSignal(activeProc.pid, 'SIGKILL', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed font-bold" title="Force immediate termination (SIGKILL 9)">SIGKILL (Force Kill)</button>
          </div>
          <div class="py-0.5">
            <button type="button" :disabled="!isOnline || isPaused(activeProc)" @click="sendSignal(activeProc.pid, 'SIGSTOP', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-gray-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="isPaused(activeProc) ? 'Process is already suspended' : 'Pause execution (SIGSTOP 19)'">SIGSTOP (Suspend)</button>
            <button type="button" :disabled="!isOnline || !isPaused(activeProc)" @click="sendSignal(activeProc.pid, 'SIGCONT', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed" :title="!isPaused(activeProc) ? 'Process is not suspended' : 'Resume execution (SIGCONT 18)'">SIGCONT (Resume)</button>
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
  processes: { type: Array, default: () => [] },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})

const emit = defineEmits(['kill-process', 'refresh'])

const search = ref('')
const sortKey = ref('cpu')
const sortAsc = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const openProcId = ref(null)
const activeProc = ref(null)
const dropdownStyle = ref({})

watch(search, () => { currentPage.value = 1 })

function toggleSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = (key === 'pid' || key === 'user' || key === 'cmd') }
}

function isPaused(p) {
  return String(p?.state || '').toUpperCase().startsWith('T')
}

function isProtected(p) {
  const pid = Number(p?.pid || 0)
  const cmd = String(p?.cmd || p?.command || '').toLowerCase()
  return pid <= 1 || ['sshd', 'ssh', 'agent_pantau', 'agent-pantau', 'pantau-server', 'systemd', 'init'].some(c => cmd.includes(c))
}

function stateLabel(p) {
  const ch = String(p?.state || 'S').toUpperCase().charAt(0)
  if (ch === 'T') return 'T (Paused)'
  if (ch === 'Z') return 'Z (Zombie)'
  return ch || 'S'
}

function stateTitle(p) {
  const ch = String(p?.state || 'S').toUpperCase().charAt(0)
  if (ch === 'R') return 'Running / Active'
  if (ch === 'T') return 'Stopped / Suspended (SIGSTOP)'
  if (ch === 'Z') return 'Zombie Process'
  return 'Sleeping / Waiting'
}

function stateBadgeClass(p) {
  const ch = String(p?.state || 'S').toUpperCase().charAt(0)
  if (ch === 'R') return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  if (ch === 'T') return 'bg-amber-950 text-amber-300 border border-amber-800'
  if (ch === 'Z') return 'bg-rose-950 text-rose-300 border border-rose-800'
  return 'bg-gray-800 text-gray-400 border border-gray-700'
}

function metricColor(val) {
  const n = Number(val || 0)
  if (n > 50) return 'text-rose-400'
  if (n > 20) return 'text-amber-300'
  return 'text-gray-200'
}

function closeDropdowns() { openProcId.value = null; activeProc.value = null }

function toggleProcDropdown(p, event) {
  if (openProcId.value === p.pid) { closeDropdowns(); return }
  openProcId.value = p.pid
  activeProc.value = p
  if (event?.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const top = Math.min(rect.bottom + 4, window.innerHeight - 175)
    const left = Math.max(8, Math.min(rect.right - 205, window.innerWidth - 213))
    dropdownStyle.value = { position: 'fixed', top: `${top}px`, left: `${left}px`, width: '205px' }
  }
}

onMounted(() => {
  window.addEventListener('click', closeDropdowns)
  window.addEventListener('scroll', closeDropdowns, true)
  window.addEventListener('resize', closeDropdowns)
})
onUnmounted(() => {
  window.removeEventListener('click', closeDropdowns)
  window.removeEventListener('scroll', closeDropdowns, true)
  window.removeEventListener('resize', closeDropdowns)
})

function sendSignal(pid, signal, cmd) {
  closeDropdowns()
  const pname = (cmd || '').split(' ')[0].split('/').pop() || 'process'
  emit('kill-process', { pid, signal, pname })
}

const filteredProcesses = computed(() => {
  return (props.processes || []).filter(p => {
    if (!search.value.trim()) return true
    const q = search.value.toLowerCase()
    return String(p.pid).includes(q) || (p.user || '').toLowerCase().includes(q) || (p.cmd || p.command || '').toLowerCase().includes(q)
  }).sort((a, b) => {
    if (['pid', 'cpu', 'mem'].includes(sortKey.value)) {
      const va = Number(a[sortKey.value] ?? a[`${sortKey.value}_percent`] ?? 0)
      const vb = Number(b[sortKey.value] ?? b[`${sortKey.value}_percent`] ?? 0)
      return sortAsc.value ? (va - vb) : (vb - va)
    }
    const va = String(a[sortKey.value] || a.command || '').toLowerCase()
    const vb = String(b[sortKey.value] || b.command || '').toLowerCase()
    return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va)
  })
})

const paginatedProcesses = computed(() => {
  if (pageSize.value === 'all') return filteredProcesses.value
  const limit = parseInt(pageSize.value, 10) || 10
  return filteredProcesses.value.slice((currentPage.value - 1) * limit, currentPage.value * limit)
})
</script>
