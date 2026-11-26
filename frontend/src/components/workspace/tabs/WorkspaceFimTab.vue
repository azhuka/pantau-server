<template>
  <div class="space-y-4 font-mono">
    <!-- Card 1: Monitored Paths & Baselines -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">File Integrity Monitoring (FIM)</h3>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
              {{ (fimPaths || []).length }} monitored
            </span>
            <span v-if="anomalyCount > 0" class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-800">
              {{ anomalyCount }} anomalies
            </span>
            <span v-else class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
              All Intact
            </span>
          </div>
          <p class="text-[11px] text-gray-400 mt-0.5">Cryptographic SHA-256, permissions, and ownership baseline monitoring</p>
        </div>

        <div v-if="!isViewer" class="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            :disabled="!isOnline"
            @click="showAddPath = !showAddPath"
            class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-600/50 hover:bg-cyan-900 transition cursor-pointer text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? 'Add custom file or directory path to FIM monitoring' : 'Server offline — action disabled'"
          >
            + Add Path
          </button>
          <button
            type="button"
            :disabled="!isOnline"
            @click="$emit('fim-action', { action: 'fim_scan', params: {} })"
            class="px-2.5 py-1 rounded bg-gray-900 text-gray-200 border border-gray-700 hover:border-cyan-500/50 hover:text-cyan-300 transition cursor-pointer text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? 'Run on-demand cryptographic verification across monitored files' : 'Server offline — action disabled'"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
            <span>Scan On-Demand</span>
          </button>
        </div>
      </div>

      <!-- Inline Add Custom FIM Path Form -->
      <form v-if="showAddPath && !isViewer" @submit.prevent="submitAddPath" class="flex items-center gap-2 flex-wrap p-2.5 rounded-lg bg-[#060a14] border border-cyan-800/50 text-xs">
        <input v-model="newPathInput" type="text" required placeholder="Absolute path (e.g. /etc/nginx/nginx.conf)" class="flex-1 min-w-[240px] px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
        <button type="submit" :disabled="!isOnline" class="px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer disabled:opacity-50">Monitor Path</button>
        <button type="button" @click="showAddPath = false" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
      </form>

      <div v-if="(fimPaths || []).length === 0" class="text-xs text-gray-400 py-6 text-center">
        No monitored FIM paths reported by this host yet.
      </div>
      <div v-else class="overflow-x-auto max-h-[360px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3">{{ t('fim_col_path') }}</th>
              <th class="py-2 px-3 text-center">{{ t('fim_col_category') }}</th>
              <th class="py-2 px-3 text-center">{{ t('fim_col_status') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_size') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_hash') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_mtime') }}</th>
              <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(fp, idx) in paginatedPaths" :key="`${fp.path}-${idx}`" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 font-semibold text-cyan-300 whitespace-nowrap">{{ fp.path }}</td>
              <td class="py-2 px-3 text-center">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold" :class="fp.category === 'custom' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-gray-800 text-gray-400'">
                  {{ fp.category === 'custom' ? 'Custom' : 'System' }}
                </span>
              </td>
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold border" :class="pathStatusClass(fp.status)">
                  {{ fp.status || 'VALID' }}
                </span>
              </td>
              <td class="py-2 px-3 text-gray-300 whitespace-nowrap text-[11px]" :title="fp.size_detail || ''">{{ fp.size_human || '-' }}</td>
              <td class="py-2 px-3 text-gray-400 text-[11px] max-w-[180px] truncate">
                <button v-if="fp.sha256_hash && fp.sha256_hash !== '-'" type="button" @click="copyHash(fp.sha256_hash)" class="hover:text-cyan-300 cursor-pointer truncate max-w-full" :title="copiedHash === fp.sha256_hash ? 'Copied!' : `Click to copy: ${fp.sha256_hash}`">
                  {{ fp.sha256_hash }}
                </button>
                <span v-else>-</span>
              </td>
              <td class="py-2 px-3 text-gray-400 text-[11px] whitespace-nowrap">{{ formatTs(fp.last_checked_at) }}</td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="isViewer"
                  type="button"
                  :disabled="!fp.sha256_hash || fp.sha256_hash === '-'"
                  @click="copyHash(fp.sha256_hash)"
                  class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 border border-gray-700 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer disabled:opacity-40"
                  title="Copy SHA-256 checksum"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="openMenu(fp, $event)"
                  class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                  title="Path integrity actions"
                >
                  <span>Actions</span>
                  <span class="text-[9px]">▾</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="pathsPage" v-model:pageSize="pathsPageSize" :total="(fimPaths || []).length" unitLabel="paths" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Card 2: FIM Change Events -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-cyan-500/20">
        <div>
          <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">Integrity Change History</h3>
          <p class="text-[11px] text-gray-400">Chronological log of file modifications, permission changes, and missing baselines</p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-[11px]">
            <button v-for="f in eventFilters" :key="f.id" type="button" @click="eventFilter = f.id" class="px-2.5 py-1 rounded transition cursor-pointer" :class="eventFilter === f.id ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'">
              {{ f.label }}
            </button>
          </div>
          <button
            v-if="!isViewer && unackCount > 0"
            type="button"
            @click="$emit('fim-ack-all')"
            class="px-2.5 py-1 rounded bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-700/60 text-emerald-300 text-[11px] font-bold cursor-pointer transition"
          >
            Acknowledge All ({{ unackCount }})
          </button>
        </div>
      </div>

      <div v-if="paginatedEvents.length === 0" class="text-xs text-gray-400 py-6 text-center">
        {{ t('fim_empty_desc') }}
      </div>
      <div v-else class="overflow-x-auto max-h-[320px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3">{{ t('th_time') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_path') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_event') }}</th>
              <th class="py-2 px-3 text-center">{{ t('fim_col_severity') }}</th>
              <th class="py-2 px-3 text-center">{{ t('fim_col_status') }}</th>
              <th class="py-2 px-3">{{ t('fim_col_details') }}</th>
              <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(ev, idx) in paginatedEvents" :key="ev.id || idx" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 text-gray-400 whitespace-nowrap text-[11px]">{{ formatTs(ev.detected_at) }}</td>
              <td class="py-2 px-3 text-cyan-300 font-semibold whitespace-nowrap">{{ ev.path }}</td>
              <td class="py-2 px-3 text-gray-200 whitespace-nowrap">{{ ev.event_type }}</td>
              <td class="py-2 px-3 text-center">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase" :class="ev.severity === 'critical' || ev.severity === 'danger' ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-amber-950 text-amber-300 border border-amber-800'">
                  {{ ev.severity || 'warning' }}
                </span>
              </td>
              <td class="py-2 px-3 text-center">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold" :class="ev.acknowledged ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'">
                  {{ ev.acknowledged ? 'ACK' : 'NEW' }}
                </span>
              </td>
              <td class="py-2 px-3 text-gray-400 truncate max-w-xs" :title="ev.details || ''">{{ ev.details || '-' }}</td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="!isViewer && !ev.acknowledged"
                  type="button"
                  @click="$emit('fim-ack', ev.id)"
                  class="px-2 py-0.5 rounded bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-700/60 text-emerald-300 text-[11px] font-bold cursor-pointer"
                >
                  Ack
                </button>
                <span v-else class="text-gray-500 text-[11px]">{{ ev.acknowledged_by || '-' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="eventsPage" v-model:pageSize="eventsPageSize" :total="filteredEvents.length" unitLabel="events" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Floating FIM Path Actions Dropdown -->
    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div class="py-0.5">
          <button type="button" :disabled="!isOnline" @click="execPathAction('fim_scan', menuTarget.path)" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Scan Now</button>
          <button v-if="menuTarget.sha256_hash && menuTarget.sha256_hash !== '-'" type="button" @click="copyHash(menuTarget.sha256_hash); menuTarget = null" class="w-full px-3 py-1.5 text-left text-gray-200 hover:bg-gray-800/80 cursor-pointer">Copy Checksum</button>
          <button type="button" :disabled="!isOnline" @click="execPathAction('fim_rebaseline', menuTarget.path)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Rebaseline</button>
          <button v-if="menuTarget.category === 'custom'" type="button" :disabled="!isOnline" @click="execPathAction('fim_path_remove', menuTarget.path)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Remove Path</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  fimPaths: { type: Array, default: () => [] },
  fimEvents: { type: Array, default: () => [] },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})

const emit = defineEmits(['fim-action', 'fim-ack', 'fim-ack-all'])

const showAddPath = ref(false)
const newPathInput = ref('')
const copiedHash = ref('')
const eventFilter = ref('all')
const pathsPage = ref(1)
const pathsPageSize = ref(10)
const eventsPage = ref(1)
const eventsPageSize = ref(10)
const menuTarget = ref(null)
const dropdownPos = ref({ top: 0, left: 0 })

const eventFilters = [
  { id: 'all', label: 'All' },
  { id: 'new', label: 'Unacknowledged' },
  { id: 'ack', label: 'Acknowledged' },
]

watch(eventFilter, () => { eventsPage.value = 1 })

const anomalyCount = computed(() => (props.fimPaths || []).filter(p => ['CHANGED', 'MISSING', 'ERROR', 'MODIFIED'].includes(p.status)).length)
const unackCount = computed(() => (props.fimEvents || []).filter(e => !e.acknowledged).length)

const paginatedPaths = computed(() => {
  const list = props.fimPaths || []
  if (pathsPageSize.value === 'all') return list
  const lim = parseInt(pathsPageSize.value, 10) || 10
  return list.slice((pathsPage.value - 1) * lim, pathsPage.value * lim)
})

const filteredEvents = computed(() => {
  return (props.fimEvents || []).filter(e => {
    if (eventFilter.value === 'new') return !e.acknowledged
    if (eventFilter.value === 'ack') return Boolean(e.acknowledged)
    return true
  })
})

const paginatedEvents = computed(() => {
  if (eventsPageSize.value === 'all') return filteredEvents.value
  const lim = parseInt(eventsPageSize.value, 10) || 10
  return filteredEvents.value.slice((eventsPage.value - 1) * lim, eventsPage.value * lim)
})

function pathStatusClass(st) {
  if (st === 'CHANGED' || st === 'MODIFIED' || st === 'ERROR') return 'bg-rose-950 text-rose-300 border-rose-700'
  if (st === 'MISSING') return 'bg-amber-950 text-amber-300 border-amber-700'
  if (st === 'NOT_CONFIGURED') return 'bg-gray-800 text-gray-400 border-gray-700'
  return 'bg-emerald-950 text-emerald-300 border-emerald-700'
}

function formatTs(ts) {
  if (!ts) return '-'
  try { return new Date(ts).toLocaleString() } catch { return ts }
}

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: '175px',
}))

function openMenu(fp, event) {
  if (menuTarget.value === fp) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 150),
    left: Math.max(8, Math.min(rect.right - 175, window.innerWidth - 183)),
  }
  menuTarget.value = fp
}

function execPathAction(action, path) {
  menuTarget.value = null
  emit('fim-action', { action, params: { path } })
}

function submitAddPath() {
  const p = newPathInput.value.trim()
  if (!p) return
  emit('fim-action', { action: 'fim_path_add', params: { path: p } })
  newPathInput.value = ''
  showAddPath.value = false
}

async function copyHash(hash) {
  if (!hash) return
  try {
    await navigator.clipboard.writeText(hash)
    copiedHash.value = hash
    setTimeout(() => { copiedHash.value = '' }, 1800)
  } catch (e) {}
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>
