<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-card p-4 rounded-xl flex items-center justify-between">
      <div>
        <h2 class="text-base font-bold text-gray-100 uppercase tracking-wide flex items-center gap-2">
          <span>📋</span>
          <span>{{ t('audit_title') }}</span>
        </h2>
        <p class="text-xs text-gray-400 mt-0.5">
          {{ t('audit_subtitle') }}
        </p>
      </div>
      <button
        @click="loadAuditLogs"
        class="px-3 py-1.5 text-xs font-semibold rounded-md bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600 hover:text-white transition cursor-pointer"
      >
        🔄 {{ t('audit_reload') }}
      </button>
    </div>

    <!-- Audit Table -->
    <div class="hud-card rounded-xl overflow-hidden shadow-xl">
      <div v-if="loading" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_loading') }}
      </div>
      <div v-else-if="auditLogs.length === 0" class="p-8 text-center text-xs text-gray-400 font-mono">
        {{ t('audit_empty') }}
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm border-collapse">
          <thead>
            <tr class="bg-[#0e1626] border-b border-gray-800 text-xs uppercase font-bold text-gray-400 tracking-wider">
              <th class="py-2.5 px-4 w-36">{{ t('audit_col_time') }}</th>
              <th class="py-2.5 px-4 w-32">{{ t('audit_col_operator') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_target') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('audit_col_action') }}</th>
              <th class="py-2.5 px-4">{{ t('audit_col_param') }}</th>
              <th class="py-2.5 px-4 w-28 text-center">{{ t('audit_col_status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 bg-[#090d16]/70">
            <tr v-for="log in auditLogs" :key="log.id" class="hover:bg-blue-600/10 transition">
              <td class="py-2.5 px-4 text-gray-400 font-mono text-xs whitespace-nowrap">{{ log.created_at || '-' }}</td>
              <td class="py-2.5 px-4 font-bold text-gray-100 whitespace-nowrap">{{ log.username }}</td>
              <td class="py-2.5 px-4 text-blue-400 whitespace-nowrap font-semibold">{{ log.server_name || `#${log.server_id}` }}</td>
              <td class="py-2.5 px-4 whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-xs font-bold font-mono bg-blue-950 text-blue-300 border border-blue-800/50">
                  {{ log.action }}
                </span>
              </td>
              <td
                class="py-2.5 px-4 text-gray-300 font-mono text-xs truncate max-w-xs cursor-help hover:text-cyan-300"
                v-tooltip="{ title: 'Audit Target', text: log.target || '-', code: true, copyable: true, extra: `Action: ${log.action} · Actor: ${log.username}` }"
              >
                {{ log.target }}
              </td>
              <td class="py-2.5 px-4 text-center whitespace-nowrap">
                <span class="px-2 py-0.5 rounded text-xs font-bold font-mono bg-emerald-950 text-emerald-400 border border-emerald-800/50">
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
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch('/api/servers', {
      headers: { Authorization: `Bearer ${token}` }
    })
    // For initial preview, audit logs will expand with full endpoint in Phase 5
    auditLogs.value = []
  } catch (err) {
    console.error('Error loading audit logs:', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAuditLogs()
})
</script>
