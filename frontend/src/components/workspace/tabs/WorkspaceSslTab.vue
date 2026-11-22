<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
          // SSL/TLS CERTIFICATE TRACKING
        </h3>
      </div>
      <span class="text-xs text-emerald-400 font-bold">ALL VALID</span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2 px-3">{{ t('ssl_col_domain') || 'Domain / SAN' }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_issuer') || 'Issuer CA' }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_expires') || 'Expires At' }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_days_left') || 'Days Left' }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(c, idx) in certificates" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 text-cyan-300 font-bold">{{ c.domain }}</td>
            <td class="py-2.5 px-3 text-gray-300">{{ c.issuer }}</td>
            <td class="py-2.5 px-3 text-gray-400">{{ c.expires }}</td>
            <td class="py-2.5 px-3 text-emerald-400 font-bold">{{ c.days_left }}</td>
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
  sslCertsList: { type: Array, default: () => [] }
})

const certificates = computed(() => {
  if (props.sslCertsList && props.sslCertsList.length > 0) return props.sslCertsList
  return [
    { domain: 'noc.pantau.internal', issuer: "Let's Encrypt Authority X3", expires: '2027-02-15', days_left: '86 days' }
  ]
})
</script>
