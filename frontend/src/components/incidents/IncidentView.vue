<template>
  <div class="space-y-6 font-mono select-none">
    <!-- Top Header Bar -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-gray-800">
      <div>
        <h2 class="text-lg font-bold text-gray-100 flex items-center gap-2 tracking-wide uppercase">
          <span class="text-cyan-400 font-extrabold">// 02</span>
          <span>{{ t('inc_title') }}</span>
        </h2>
        <p class="text-xs text-gray-400 mt-1 max-w-2xl leading-relaxed">
          {{ t('inc_subtitle') }}
        </p>
      </div>

      <div class="flex items-center gap-2">
        <!-- Global Thresholds Button -->
        <button
          v-if="canManageThresholds"
          @click="showThresholdModal = true"
          class="px-3 py-1.5 rounded bg-[#060a14] border border-cyan-800/60 hover:border-cyan-400 text-cyan-300 font-bold text-xs transition cursor-pointer flex items-center gap-2 shadow-sm"
          :title="t('inc_btn_thresholds')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>{{ t('inc_btn_thresholds') }}</span>
        </button>

        <!-- Refresh Button -->
        <button
          @click="refreshAll"
          class="p-1.5 rounded bg-[#060a14] border border-gray-800 hover:border-gray-600 text-gray-300 hover:text-white transition cursor-pointer"
          :title="t('dash_sync_tooltip') || 'Refresh'"
        >
          <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Table 1: Insiden Aktif (Active Physical Incidents) -->
    <ActiveIncidentsTable
      :problems="activeProblems"
      :servers="servers"
      :current-user="currentUser"
      @ack="handleAck"
      @unignore="handleUnignore"
      @open-ignore-modal="openIgnoreModal"
      @open-workspace="handleOpenWorkspace"
    />

    <!-- Table 2: Riwayat Insiden Teratasi (Resolved Incidents & MTTR Analytics) -->
    <ResolvedIncidentsTable
      :problems="resolvedProblems"
      :servers="servers"
      :stats="stats.resolved"
      v-model:period="resolvedPeriod"
      v-model:start-date="resolvedStartDate"
      v-model:end-date="resolvedEndDate"
      @open-workspace="handleOpenWorkspace"
    />

    <!-- Modal 1: Ignore Incident Modal -->
    <IgnoreIncidentModal
      :is-open="showIgnoreModal"
      :problem="selectedProblem"
      :current-user="currentUser"
      @close="showIgnoreModal = false"
      @ignored="onIgnored"
    />

    <!-- Modal 2: Global Alert Thresholds Modal -->
    <IncidentThresholdModal
      :is-open="showThresholdModal"
      :thresholds="thresholds"
      :current-user="currentUser"
      @close="showThresholdModal = false"
      @saved="onThresholdsSaved"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from '../../i18n'
import ActiveIncidentsTable from './ActiveIncidentsTable.vue'
import ResolvedIncidentsTable from './ResolvedIncidentsTable.vue'
import IgnoreIncidentModal from './modals/IgnoreIncidentModal.vue'
import IncidentThresholdModal from './modals/IncidentThresholdModal.vue'
import { useToast } from '../../utils/useToast'

const { t } = useI18n()
const toast = useToast()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['open-workspace'])

const activeProblems = ref([])
const resolvedProblems = ref([])
const stats = ref({ active: {}, resolved: {} })
const thresholds = ref({})
const resolvedPeriod = ref('24h')
const resolvedStartDate = ref('')
const resolvedEndDate = ref('')
const loading = ref(false)

const showIgnoreModal = ref(false)
const selectedProblem = ref(null)
const showThresholdModal = ref(false)

const canManageThresholds = computed(() => {
  const r = (props.currentUser?.role || '').toLowerCase()
  return !['viewer', 'guest', 'tamu'].includes(r)
})

function getAuthHeaders() {
  const token = localStorage.getItem('pantau_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  }
}

async function fetchActiveProblems() {
  try {
    const res = await fetch('/api/problems?active_only=true', { headers: getAuthHeaders() })
    const data = await res.json()
    if (data.ok) activeProblems.value = data.problems || []
  } catch (err) { console.error('fetchActiveProblems error:', err) }
}

async function fetchResolvedProblems() {
  try {
    const params = new URLSearchParams({
      active_only: 'false',
      period: resolvedPeriod.value || '24h',
      limit: '300',
    })
    if (resolvedStartDate.value) params.set('start_date', resolvedStartDate.value)
    if (resolvedEndDate.value) params.set('end_date', resolvedEndDate.value)
    const res = await fetch(`/api/problems?${params.toString()}`, { headers: getAuthHeaders() })
    const data = await res.json()
    if (data.ok) resolvedProblems.value = data.problems || []
  } catch (err) { console.error('fetchResolvedProblems error:', err) }
}

async function fetchStats() {
  try {
    const res = await fetch('/api/problems/stats', { headers: getAuthHeaders() })
    const data = await res.json()
    if (data.ok) stats.value = data
  } catch (err) { console.error('fetchStats error:', err) }
}

async function fetchThresholds() {
  try {
    const res = await fetch('/api/problems/thresholds', { headers: getAuthHeaders() })
    const data = await res.json()
    if (data.ok) thresholds.value = data.thresholds || {}
  } catch (err) { console.error('fetchThresholds error:', err) }
}

async function refreshAll() {
  loading.value = true
  await Promise.allSettled([
    fetchActiveProblems(),
    fetchResolvedProblems(),
    fetchStats(),
    fetchThresholds()
  ])
  loading.value = false
}

async function handleAck(probId) {
  try {
    const res = await fetch(`/api/problems/${probId}/ack`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    const data = await res.json()
    if (data.ok) {
      const idx = activeProblems.value.findIndex(p => p.id === probId)
      if (idx !== -1) {
        activeProblems.value[idx].acknowledged_by = data.acknowledged_by
        activeProblems.value[idx].acknowledged_at = data.acknowledged_at
      }
    } else {
      toast.error(data.detail || 'Failed to acknowledge incident')
    }
  } catch (err) {
    console.error('Error acknowledging incident:', err)
  }
}

async function handleUnignore(probId) {
  try {
    const res = await fetch(`/api/problems/${probId}/unignore`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    const data = await res.json()
    if (data.ok) {
      await refreshAll()
    } else {
      toast.error(data.detail || 'Failed to cancel ignore incident')
    }
  } catch (err) {
    console.error('Error unignoring incident:', err)
  }
}

function openIgnoreModal(prob) {
  selectedProblem.value = prob
  showIgnoreModal.value = true
}

async function onIgnored() {
  await refreshAll()
}

function onThresholdsSaved(newTh) {
  thresholds.value = newTh
}

function handleOpenWorkspace(payload) {
  emit('open-workspace', payload)
}

watch([resolvedPeriod, resolvedStartDate, resolvedEndDate], ([p, s, e]) => {
  if (p === 'custom' && !s && !e) return
  fetchResolvedProblems()
})

onMounted(() => {
  refreshAll()
})
</script>