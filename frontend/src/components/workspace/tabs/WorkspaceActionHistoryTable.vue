<template>
  <div class="space-y-2.5 pt-2">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div>
        <h4 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">
          // Action History
        </h4>
        <p class="text-[11px] text-gray-500">Audit trail of operator actions and commands executed from Pantau Server</p>
      </div>
      <span class="text-xs text-gray-400">{{ actions.length }} actions</span>
    </div>

    <div v-if="loading" class="bg-[#0b1220] border border-gray-800/80 rounded-xl p-6 text-center text-xs text-gray-400">
      Loading action history...
    </div>

    <div v-else-if="actions.length === 0" class="bg-[#0b1220] border border-gray-800/80 rounded-xl p-6 text-center text-xs text-gray-500">
      No application action history recorded for this server.
    </div>

    <div v-else class="bg-[#0b1220] border border-gray-800/80 rounded-xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="bg-[#080d1a] border-b border-gray-800 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th class="py-2.5 px-3 whitespace-nowrap">{{ t('dash_col_time') }}</th>
              <th class="py-2.5 px-3 whitespace-nowrap">{{ t('audit_col_operator') }}</th>
              <th class="py-2.5 px-3 whitespace-nowrap">{{ t('ws_col_action') }}</th>
              <th class="py-2.5 px-3">{{ t('audit_col_target') }}</th>
              <th class="py-2.5 px-3 text-center whitespace-nowrap">{{ t('col_status') }}</th>
              <th class="py-2.5 px-3">{{ t('audit_col_result') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr v-for="act in pagedActions" :key="act.id" class="hover:bg-gray-800/30 transition-colors">
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap" :title="`Execution Time: ${act.time || '-'}`">
                {{ formatIncidentTime(act.time) }}
              </td>
              <td class="py-2.5 px-3 font-semibold text-gray-200 whitespace-nowrap">
                {{ act.user || 'System' }}
              </td>
              <td class="py-2.5 px-3 whitespace-nowrap">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-800 text-cyan-300 border border-gray-700">
                  {{ act.action_label || act.action }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-200 font-medium max-w-[220px] truncate" :title="act.target || '-'">
                {{ act.target || '-' }}
              </td>
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase border" :class="statusBadgeClass(act.status)">
                  {{ (act.status || 'INFO').toUpperCase() }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-400 max-w-xs truncate" :title="act.result || '-'">
                {{ act.result || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination
        v-model:page="currentPage"
        v-model:pageSize="pageSize"
        :total="actions.length"
        unitLabel="actions"
        :pageSizeOptions="[10, 25, 50, 100, 'all']"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from '../../../i18n'
import { formatIncidentTime } from '../../../utils/formatters'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  serverId: { type: Number, required: true },
  refreshKey: { type: Number, default: 0 },
})

const actions = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)

const pagedActions = computed(() => {
  if (pageSize.value === 'all') return actions.value
  const start = (currentPage.value - 1) * pageSize.value
  return actions.value.slice(start, start + pageSize.value)
})

function statusBadgeClass(st) {
  const s = (st || '').toUpperCase()
  if (['SUCCESS', 'EXECUTED', 'RESOLVED', 'OK'].includes(s)) return 'bg-emerald-950/70 text-emerald-300 border-emerald-700/60'
  if (['FAILED', 'ERROR', 'DETECTED'].includes(s)) return 'bg-rose-950/70 text-rose-300 border-rose-700/60'
  if (['PENDING', 'EXECUTING', 'QUEUED'].includes(s)) return 'bg-amber-950/70 text-amber-300 border-amber-700/60'
  return 'bg-gray-800 text-gray-300 border-gray-700'
}

async function fetchActions() {
  if (!props.serverId) return
  loading.value = actions.value.length === 0
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/actions?limit=100`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (data.ok) actions.value = data.actions || []
  } catch (e) {
    // keep existing list on transient error
  } finally {
    loading.value = false
  }
}

watch(() => [props.serverId, props.refreshKey], () => {
  currentPage.value = 1
  fetchActions()
})

onMounted(fetchActions)
</script>
