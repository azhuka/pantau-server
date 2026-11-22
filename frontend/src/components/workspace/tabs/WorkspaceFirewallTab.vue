<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_fw_title') }}</h3>
        <span
          class="px-2 py-0.5 rounded text-[11px] uppercase font-bold"
          :class="firewallData?.status === 'active' ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60' : 'bg-gray-800 text-gray-400'"
        >
          {{ firewallData?.status || 'unknown' }}
        </span>
      </div>
    </div>
    <div v-if="(firewallData?.rules || []).length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
      {{ t('ws_fw_empty') }}
    </div>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2.5 px-3">{{ t('ws_col_to') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_action') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_from') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(r, idx) in firewallData.rules" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 font-semibold text-gray-200">{{ r.to || r.target }}</td>
            <td class="py-2.5 px-3">
              <span class="text-emerald-400 font-bold">{{ r.action || 'ALLOW' }}</span>
            </td>
            <td class="py-2.5 px-3 text-gray-400">{{ r.from || 'Anywhere' }}</td>
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
  firewallData: { type: Object, default: () => ({ status: 'unknown', rules: [] }) }
})
</script>
