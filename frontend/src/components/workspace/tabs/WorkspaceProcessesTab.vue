<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_procs_title') }}</h3>
        <span class="text-xs text-gray-400">({{ filteredProcesses.length }})</span>
      </div>
    </div>

    <NocFilterPanel
      class="mb-3"
      :has-active-filters="Boolean(userFilter || search.trim())"
      :summary-text="`${filteredProcesses.length} of ${(processes || []).length} processes`"
      compact
      @reset="userFilter = ''; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="proc-user-filter">{{ t('ws_col_user') }}</label>
          <select id="proc-user-filter" v-model="userFilter" class="noc-filter-select max-w-[145px]">
            <option value="">All Users</option>
            <option v-for="u in uniqueUsers" :key="u" :value="u">{{ u }}</option>
          </select>
        </div>
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
            <th class="py-2.5 px-3">{{ t('ws_col_pid') || 'PID' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
            <th class="py-2.5 px-3">{{ t('col_cpu_pct') || 'CPU %' }}</th>
            <th class="py-2.5 px-3">{{ t('col_ram_pct') || 'RAM %' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_command') }}</th>
            <th class="py-2.5 px-3 text-right">{{ t('col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(p, idx) in paginatedProcesses" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 text-cyan-400 font-bold">{{ p.pid }}</td>
            <td class="py-2.5 px-3 text-gray-300">{{ p.user }}</td>
            <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.cpu || p.cpu_percent || 0 }}%</td>
            <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.mem || p.mem_percent || 0 }}%</td>
            <td
              class="py-2.5 px-3 text-gray-400 truncate max-w-sm cursor-help hover:text-cyan-200"
              :title="p.cmd || p.command"
            >
              {{ p.cmd || p.command }}
            </td>
            <td class="py-2.5 px-3 text-right">
              <div class="relative inline-block text-left">
                <button
                  type="button"
                  @click.stop="toggleProcDropdown(p, $event)"
                  class="p-1.5 rounded bg-gray-900 hover:bg-rose-950 border border-gray-700 hover:border-rose-600/50 text-gray-300 hover:text-rose-300 transition cursor-pointer flex items-center justify-center shadow-sm"
                  :title="t('col_actions')"
                >
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="1.5"></circle>
                    <circle cx="12" cy="5" r="1.5"></circle>
                    <circle cx="12" cy="19" r="1.5"></circle>
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Universal Table Pagination Bar (Hidden if <= 10 items) -->
    <NocTablePagination
      v-model:page="currentPage"
      v-model:pageSize="pageSize"
      :total="filteredProcesses.length"
      unitLabel="processes"
      :pageSizeOptions="[10, 25, 50, 100, 'all']"
    />

    <!-- Floating Process Action Dropdown Menu (Teleported to body to eliminate scroll clipping) -->
    <Teleport to="body">
      <div
        v-if="openProcId && activeProc"
        @click.stop
        :style="dropdownStyle"
        class="rounded-lg bg-[#0b1326] border border-rose-900/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 transition-all select-none"
      >
        <div class="py-0.5">
          <button type="button" @click="sendSignal(activeProc.pid, 'SIGTERM', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:text-white hover:bg-amber-950/80 flex items-center gap-2 cursor-pointer transition font-bold" title="Request process to close gracefully (SIGTERM 15)">
            <span>SIGTERM (Terminate)</span>
          </button>
          <button type="button" @click="sendSignal(activeProc.pid, 'SIGKILL', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:text-white hover:bg-rose-950/80 flex items-center gap-2 cursor-pointer transition font-bold" title="Force immediate termination without catch (SIGKILL 9)">
            <span>SIGKILL (Force Kill)</span>
          </button>
        </div>
        <div class="py-0.5">
          <button type="button" @click="sendSignal(activeProc.pid, 'SIGSTOP', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-gray-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition" title="Pause execution (SIGSTOP 19)">
            <span>SIGSTOP (Suspend)</span>
          </button>
          <button type="button" @click="sendSignal(activeProc.pid, 'SIGCONT', activeProc.cmd || activeProc.command)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:text-white hover:bg-emerald-950/80 flex items-center gap-2 cursor-pointer transition" title="Resume execution (SIGCONT 18)">
            <span>SIGCONT (Resume)</span>
          </button>
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

const { t } = useI18n()

const props = defineProps({
  processes: { type: Array, default: () => [] }
})

const emit = defineEmits(['kill-process'])

const search = ref('')
const userFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const openProcId = ref(null)
const activeProc = ref(null)
const dropdownStyle = ref({})

const uniqueUsers = computed(() => Array.from(new Set((props.processes || []).map(p => p.user).filter(Boolean))).sort())

watch([search, userFilter], () => {
  currentPage.value = 1
})

function closeDropdowns() {
  openProcId.value = null
  activeProc.value = null
}

function toggleProcDropdown(p, event) {
  if (openProcId.value === p.pid) {
    closeDropdowns()
    return
  }
  openProcId.value = p.pid
  activeProc.value = p

  if (event && event.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const vh = window.innerHeight
    const vw = window.innerWidth
    const menuHeight = 170
    const spaceBelow = vh - rect.bottom
    const spaceAbove = rect.top
    const isDropup = (spaceBelow < menuHeight + 10) && (spaceAbove > spaceBelow)
    const rightOffset = Math.max(8, vw - rect.right)

    if (isDropup) {
      dropdownStyle.value = {
        position: 'fixed',
        bottom: `${Math.max(8, vh - rect.top + 4)}px`,
        right: `${rightOffset}px`,
        zIndex: 100005,
        width: '176px'
      }
    } else {
      dropdownStyle.value = {
        position: 'fixed',
        top: `${Math.max(8, rect.bottom + 4)}px`,
        right: `${rightOffset}px`,
        zIndex: 100005,
        width: '176px'
      }
    }
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
    if (userFilter.value && p.user !== userFilter.value) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      return String(p.pid).includes(q) || (p.user || '').toLowerCase().includes(q) || (p.cmd || p.command || '').toLowerCase().includes(q)
    }
    return true
  })
})

const paginatedProcesses = computed(() => {
  if (pageSize.value === 'all') return filteredProcesses.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredProcesses.value.slice(start, start + limit)
})
</script>
