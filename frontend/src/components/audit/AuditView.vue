<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// SYSTEM AUDIT TRAIL</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('audit_subtitle') }}
        </p>
      </div>
      <button
        @click="loadAuditLogs"
        class="px-2.5 py-1 text-xs font-mono font-bold rounded bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-800 hover:text-white transition cursor-pointer flex items-center gap-1.5"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
          <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
          <path d="M16 21h5v-5"/>
        </svg>
        <span>{{ t('audit_reload') }}</span>
      </button>
    </div>

    <!-- Audit Table -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl mb-8">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div v-if="loading" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_loading') }}
      </div>
      <div v-else-if="auditLogs.length === 0" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_empty') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider select-none">
              <th class="py-2.5 px-4 w-36">{{ t('audit_col_time') }}</th>
              <th class="py-2.5 px-4 w-32">{{ t('audit_col_operator') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_target') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_action') }}</th>
              <th class="py-2.5 px-4">{{ t('audit_col_param') }}</th>
              <th class="py-2.5 px-4 w-28 text-center">{{ t('audit_col_status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr v-for="log in auditLogs" :key="log.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">{{ log.created_at || '-' }}</td>
              <td class="py-2.5 px-4 font-bold text-gray-100 whitespace-nowrap">{{ log.username }}</td>
              <td class="py-2.5 px-4 text-cyan-400 whitespace-nowrap font-semibold">{{ log.server_name || `#${log.server_id}` }}</td>
              <td class="py-2.5 px-4 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">
                  {{ log.action }}
                </span>
              </td>
              <td
                class="py-2.5 px-4 text-gray-300 truncate max-w-xs cursor-help hover:text-cyan-300"
                :title="log.target"
              >
                {{ log.target }}
              </td>
              <td class="py-2.5 px-4 text-center whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                  {{ log.result || 'SUCCESS' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from '../../i18n'

const { t } = useI18n()

const loading = ref(false)
const auditLogs = ref([])

async function loadAuditLogs() {
  loading.value = true
  try {
    const res = await fetch('/api/audit?limit=50')
    if (res.ok) {
      auditLogs.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load audit logs:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAuditLogs()
})
</script>
