<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_cron_title') }}</h3>
      <span class="text-xs text-gray-400">{{ (cronData?.jobs || []).length }} tasks</span>
    </div>
    <div v-if="(cronData?.jobs || []).length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
      {{ t('ws_cron_empty') }}
    </div>
    <div v-else class="overflow-x-auto max-h-[500px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
          <tr class="text-gray-400 uppercase font-bold tracking-wider">
            <th class="py-2.5 px-3">{{ t('ws_col_schedule') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_exec') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_source') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(j, idx) in cronData?.jobs || []" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 font-bold text-amber-300">{{ j.schedule }}</td>
            <td class="py-2.5 px-3 text-gray-300 font-medium">{{ j.user || 'root' }}</td>
            <td
              class="py-2.5 px-3 text-gray-200 truncate max-w-md cursor-help hover:text-cyan-200"
              :title="j.command"
            >
              {{ j.command }}
            </td>
            <td class="py-2.5 px-3 text-gray-400">{{ j.source || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../../i18n'

const { t } = useI18n()

defineProps({
  cronData: { type: Object, default: () => ({ jobs: [] }) }
})
</script>
