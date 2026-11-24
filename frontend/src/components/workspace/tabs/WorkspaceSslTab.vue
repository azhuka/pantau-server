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
      <span class="text-xs font-bold" :class="certificates.length > 0 ? 'text-emerald-400' : 'text-gray-400'">
        {{ certificates.length > 0 ? `${certificates.length} ACTIVE` : '0 DISCOVERED' }}
      </span>
    </div>

    <!-- Empty State when no SSL certs found on this host -->
    <div v-if="certificates.length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
      <svg class="w-8 h-8 text-gray-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
      <div>{{ t('ssl_empty_desc') || 'No SSL/TLS certificates discovered on this host.' }}</div>
      <div class="text-[11px] text-gray-500 mt-1">{{ t('ssl_empty_hint') || 'Certificates are tracked from standard web server stores (/etc/letsencrypt, /etc/ssl).' }}</div>
    </div>

    <!-- Real SSL Certificates Table -->
    <div v-else class="overflow-x-auto">
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
  if (props.sslCertsList && Array.isArray(props.sslCertsList) && props.sslCertsList.length > 0) {
    return props.sslCertsList
  }
  return []
})
</script>
