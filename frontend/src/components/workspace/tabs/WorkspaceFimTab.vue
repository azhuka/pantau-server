<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
          // FILE INTEGRITY MONITORING (FIM)
        </h3>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          @click="$emit('fim-action', { action: 'fim_scan', params: {} })"
          class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-600/50 hover:bg-cyan-700 hover:text-white transition cursor-pointer text-xs font-bold inline-flex items-center gap-1.5"
          title="Run cryptographic hash verification across monitored system files"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
          </svg>
          <span>Scan On-Demand</span>
        </button>
      </div>
    </div>

    <!-- Empty State when no FIM events recorded -->
    <div v-if="fimList.length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
      <svg class="w-8 h-8 text-gray-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        <path d="m9 12 2 2 4-4"/>
      </svg>
      <div>{{ t('fim_empty_desc') || 'No file integrity modifications or anomalies recorded.' }}</div>
      <div class="text-[11px] text-gray-500 mt-1">{{ t('fim_clean_hint') || 'System baselines (/etc/passwd, sshd_config, sudoers) are intact.' }}</div>
    </div>

    <!-- Real FIM Table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2 px-3">{{ t('fim_col_path') || 'Monitored Path' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_status') || 'Status' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_hash') || 'SHA-256 Hash' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_mtime') || 'Last Verified' }}</th>
            <th class="py-2 px-3 text-right">{{ t('col_actions') || 'Actions' }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(item, idx) in fimList" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 text-cyan-300 font-semibold">{{ item.path }}</td>
            <td class="py-2.5 px-3">
              <span
                class="px-2 py-0.5 rounded text-[10px] font-bold"
                :class="item.status === 'MODIFIED' || item.status === 'ANOMALY' ? 'bg-rose-950 text-rose-300 border border-rose-700' : 'bg-emerald-950 text-emerald-300 border border-emerald-700'"
              >
                {{ item.status || 'CLEAN' }}
              </span>
            </td>
            <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px] truncate max-w-xs">{{ item.hash || '-' }}</td>
            <td class="py-2.5 px-3 text-gray-400">{{ item.mtime || 'Verified' }}</td>
            <td class="py-2.5 px-3 text-right">
              <button
                type="button"
                @click="$emit('fim-action', { action: 'fim_rebaseline', params: { path: item.path } })"
                class="px-2 py-0.5 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer"
                title="Accept current hash as new legitimate baseline"
              >
                Rebaseline
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  fimEvents: { type: Array, default: () => [] }
})

defineEmits(['fim-action'])

const fimList = computed(() => {
  if (props.fimEvents && Array.isArray(props.fimEvents) && props.fimEvents.length > 0) {
    return props.fimEvents
  }
  return []
})
</script>
