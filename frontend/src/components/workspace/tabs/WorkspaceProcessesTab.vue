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
              <button
                @click="$emit('kill-process', p.pid)"
                class="px-2.5 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white transition cursor-pointer text-xs font-bold inline-flex items-center gap-1.5"
                :title="`Terminate process PID ${p.pid} (${p.user})`"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="15" y1="9" x2="9" y2="15"/>
                  <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <span>{{ t('ws_act_kill') }}</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  processes: { type: Array, default: () => [] }
})

defineEmits(['kill-process'])

const search = ref('')

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
