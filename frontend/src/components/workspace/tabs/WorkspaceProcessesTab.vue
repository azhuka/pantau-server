<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_procs_title') }}</h3>
        <span class="text-xs text-gray-400">({{ (processes || []).length }})</span>
      </div>
      <input
        v-model="search"
        type="text"
        :placeholder="t('ws_procs_search')"
        class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 text-gray-200 text-xs rounded px-3 py-1.5 w-60 focus:outline-none"
      />
    </div>
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
          <tr v-for="(p, idx) in filteredProcesses" :key="idx" class="hover:bg-cyan-950/20">
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
                  @click.stop="toggleProcDropdown(p.pid)"
                  class="p-1.5 rounded bg-gray-900 hover:bg-rose-950 border border-gray-700 hover:border-rose-600/50 text-gray-300 hover:text-rose-300 transition cursor-pointer flex items-center justify-center shadow-sm"
                  :title="t('col_actions')"
                >
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="1.5"></circle>
                    <circle cx="12" cy="5" r="1.5"></circle>
                    <circle cx="12" cy="19" r="1.5"></circle>
                  </svg>
                </button>

                <div
                  v-if="openProcId === p.pid"
                  @click.stop
                  class="absolute right-0 mt-1 w-44 rounded-lg bg-[#0b1326] border border-rose-900/80 shadow-2xl z-50 py-1 font-mono text-xs divide-y divide-gray-800"
                >
                  <div class="py-0.5">
                    <!-- SIGTERM: Terminate Gracefully -->
                    <button
                      type="button"
                      @click="sendSignal(p.pid, 'SIGTERM', p.cmd || p.command)"
                      class="w-full px-3 py-1.5 text-left text-amber-300 hover:text-white hover:bg-amber-950/80 flex items-center gap-2 cursor-pointer transition font-bold"
                      title="Request process to close gracefully (SIGTERM 15)"
                    >
                      <svg class="w-3.5 h-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                      <span>SIGTERM (Terminasi)</span>
                    </button>

                    <!-- SIGKILL: Force Kill -->
                    <button
                      type="button"
                      @click="sendSignal(p.pid, 'SIGKILL', p.cmd || p.command)"
                      class="w-full px-3 py-1.5 text-left text-rose-400 hover:text-white hover:bg-rose-950/80 flex items-center gap-2 cursor-pointer transition font-bold"
                      title="Force immediate termination without catch (SIGKILL 9)"
                    >
                      <svg class="w-3.5 h-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                      <span>SIGKILL (Paksa)</span>
                    </button>
                  </div>

                  <div class="py-0.5">
                    <!-- SIGSTOP: Suspend -->
                    <button
                      type="button"
                      @click="sendSignal(p.pid, 'SIGSTOP', p.cmd || p.command)"
                      class="w-full px-3 py-1.5 text-left text-gray-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
                      title="Pause execution (SIGSTOP 19)"
                    >
                      <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                      <span>SIGSTOP (Bekukan)</span>
                    </button>

                    <!-- SIGCONT: Resume -->
                    <button
                      type="button"
                      @click="sendSignal(p.pid, 'SIGCONT', p.cmd || p.command)"
                      class="w-full px-3 py-1.5 text-left text-emerald-300 hover:text-white hover:bg-emerald-950/80 flex items-center gap-2 cursor-pointer transition"
                      title="Resume execution (SIGCONT 18)"
                    >
                      <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                      <span>SIGCONT (Lanjut)</span>
                    </button>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  processes: { type: Array, default: () => [] }
})

const emit = defineEmits(['kill-process'])

const search = ref('')
const openProcId = ref(null)

function toggleProcDropdown(pid) {
  openProcId.value = openProcId.value === pid ? null : pid
}

function closeDropdowns() {
  openProcId.value = null
}

onMounted(() => {
  window.addEventListener('click', closeDropdowns)
})

onUnmounted(() => {
  window.removeEventListener('click', closeDropdowns)
})

function sendSignal(pid, signal, cmd) {
  openProcId.value = null
  const pname = (cmd || '').split(' ')[0].split('/').pop() || 'process'
  emit('kill-process', { pid, signal, pname })
}

const filteredProcesses = computed(() => {
  if (!search.value) return props.processes
  const q = search.value.toLowerCase()
  return props.processes.filter(p =>
    String(p.pid).includes(q) ||
    (p.user || '').toLowerCase().includes(q) ||
    (p.cmd || p.command || '').toLowerCase().includes(q)
  )
})
</script>
