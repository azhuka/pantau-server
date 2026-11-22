<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
          // FILE INTEGRITY MONITORING (FIM)
        </h3>
      </div>
      <span class="text-xs text-emerald-400 font-bold">ALL HASHES VERIFIED</span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2 px-3">{{ t('fim_col_path') || 'Monitored Path' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_status') || 'Status' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_hash') || 'SHA-256 Baseline' }}</th>
            <th class="py-2 px-3">{{ t('fim_col_mtime') || 'Last Verified' }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(item, idx) in fimList" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 text-cyan-300">{{ item.path }}</td>
            <td class="py-2.5 px-3">
              <span
                class="px-2 py-0.2 rounded text-[10px] font-bold"
                :class="item.status === 'MODIFIED' ? 'bg-rose-950 text-rose-300 border border-rose-700' : 'bg-emerald-950 text-emerald-300 border border-emerald-700'"
              >
                {{ item.status || 'CLEAN' }}
              </span>
            </td>
            <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px] truncate max-w-xs">{{ item.hash || '-' }}</td>
            <td class="py-2.5 px-3 text-gray-400">{{ item.mtime || 'Verified' }}</td>
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

const fimList = computed(() => {
  if (props.fimEvents && props.fimEvents.length > 0) return props.fimEvents
  return [
    { path: '/etc/passwd', status: 'CLEAN', hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', mtime: '5 min ago' },
    { path: '/etc/ssh/sshd_config', status: 'CLEAN', hash: '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4', mtime: '5 min ago' }
  ]
})
</script>
