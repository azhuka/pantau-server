<template>
  <div class="space-y-4 font-mono">
    <!-- Card 1: Cron Jobs (Scheduled Tasks) -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
        <div>
          <div class="flex items-center gap-2">
            <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">{{ t('ws_cron_title') }}</h3>
            <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
              {{ allJobs.length }} scheduled
            </span>
          </div>
          <p class="text-[11px] text-gray-400 mt-0.5">System crontab schedules (/etc/crontab &amp; /etc/cron.d/*)</p>
        </div>
        <button
          v-if="!isViewer"
          type="button"
          :disabled="!isOnline"
          @click="showAddForm = !showAddForm"
          class="px-2.5 py-1 rounded text-[11px] font-bold bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-600/50 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          :title="isOnline ? 'Add a new managed cron job' : 'Server offline — action disabled'"
        >
          + Add Cron Job
        </button>
      </div>

      <!-- Inline Add Cron Job Form -->
      <form v-if="showAddForm && !isViewer" @submit.prevent="submitAddCron" class="p-3 rounded-lg bg-[#060a14] border border-cyan-800/50 space-y-2 text-xs">
        <div class="grid grid-cols-1 sm:grid-cols-4 gap-2">
          <input v-model="addForm.ident" type="text" required placeholder="Job ID (e.g. backup-db)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
          <input v-model="addForm.user" type="text" required placeholder="Run as user (e.g. root)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
          <input v-model="addForm.schedule" type="text" required placeholder="Schedule (e.g. 0 2 * * *)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
          <select @change="applyPreset($event.target.value)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-300 outline-none">
            <option value="">Schedule Presets...</option>
            <option value="*/5 * * * *">Every 5 minutes</option>
            <option value="0 * * * *">Hourly (0 * * * *)</option>
            <option value="0 2 * * *">Daily at 02:00</option>
            <option value="0 3 * * 0">Weekly (Sunday 03:00)</option>
          </select>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <input v-model="addForm.command" type="text" required placeholder="Execution command (e.g. /usr/local/bin/backup.sh)" class="flex-1 min-w-[240px] px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
          <button type="submit" :disabled="!isOnline" class="px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer disabled:opacity-50">Save</button>
          <button type="button" @click="showAddForm = false" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
        </div>
      </form>

      <div v-if="allJobs.length === 0" class="text-xs text-gray-400 py-6 text-center">
        {{ t('ws_cron_empty') }}
      </div>
      <div v-else class="overflow-x-auto max-h-[380px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3 text-center">{{ t('col_status') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_schedule') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_user') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_exec') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_source') }}</th>
              <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(j, idx) in paginatedJobs" :key="idx" class="hover:bg-cyan-950/20" :class="{ 'opacity-60': j.is_enabled === false }">
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="j.is_enabled !== false ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-gray-800 text-gray-400 border border-gray-700'">
                  {{ j.is_enabled !== false ? 'ACTIVE' : 'PAUSED' }}
                </span>
              </td>
              <td class="py-2 px-3 font-bold text-amber-300 whitespace-nowrap">{{ j.schedule }}</td>
              <td class="py-2 px-3 text-gray-300 whitespace-nowrap">{{ j.user || 'root' }}</td>
              <td class="py-2 px-3 text-gray-200 truncate max-w-md cursor-help" :title="j.command">{{ j.command }}</td>
              <td class="py-2 px-3 text-gray-400 whitespace-nowrap text-[11px]">
                <span>{{ j.source || '-' }}{{ j.line ? `:${j.line}` : '' }}</span>
                <span v-if="j.is_managed" class="ml-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">Managed</span>
              </td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="isViewer"
                  type="button"
                  disabled
                  class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 border border-gray-700 text-gray-500 opacity-40 cursor-not-allowed inline-flex items-center justify-center"
                  title="Read-only role: cron actions are disabled"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="openMenu(j, $event)"
                  class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                  title="Cron job actions"
                >
                  <span>Actions</span>
                  <span class="text-[9px]">▾</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="jobsPage" v-model:pageSize="jobsPageSize" :total="allJobs.length" unitLabel="jobs" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Card 2: Systemd Timers -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
        <div>
          <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">Systemd Timers</h3>
          <p class="text-[11px] text-gray-400">Systemd-managed periodic timer units</p>
        </div>
        <span class="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-950/60 text-cyan-300 border border-cyan-800/60">
          {{ allTimers.length }} timers
        </span>
      </div>

      <div v-if="allTimers.length === 0" class="text-xs text-gray-400 py-5 text-center">
        No active systemd timers detected.
      </div>
      <div v-else class="overflow-x-auto max-h-[300px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3">{{ t('ws_col_timer') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_activates') }}</th>
              <th class="py-2 px-3">{{ t('ws_col_schedule_status') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(tm, idx) in paginatedTimers" :key="`${tm.timer}-${idx}`" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 font-semibold text-gray-200 whitespace-nowrap">{{ tm.timer || '-' }}</td>
              <td class="py-2 px-3 text-emerald-400 whitespace-nowrap">{{ tm.activates || '-' }}</td>
              <td class="py-2 px-3 text-gray-400 text-[11px]">{{ tm.raw || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="timersPage" v-model:pageSize="timersPageSize" :total="allTimers.length" unitLabel="timers" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Floating Cron Actions Dropdown -->
    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div class="py-0.5">
          <button type="button" :disabled="!isOnline" @click="runCron(menuTarget)" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Run Now</button>
          <template v-if="menuTarget.is_managed && menuTarget.ident">
            <button type="button" :disabled="!isOnline" @click="toggleCron(menuTarget)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
              {{ menuTarget.is_enabled !== false ? 'Pause Cron' : 'Enable Cron' }}
            </button>
            <button type="button" :disabled="!isOnline" @click="deleteCron(menuTarget)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Delete Cron</button>
          </template>
          <div v-else class="px-3 py-1.5 text-[11px] text-gray-500">Protected System Cron</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocTablePagination from '../../common/NocTablePagination.vue'
import { confirmAction } from '../../../utils/useToast'

const { t } = useI18n()
const props = defineProps({
  cronData: { type: Object, default: () => ({ jobs: [], timers: [] }) },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})
const emit = defineEmits(['cron-action'])

const showAddForm = ref(false)
const addForm = ref({ ident: '', user: 'root', schedule: '0 2 * * *', command: '' })
const jobsPage = ref(1)
const jobsPageSize = ref(10)
const timersPage = ref(1)
const timersPageSize = ref(10)
const menuTarget = ref(null)
const dropdownPos = ref({ top: 0, left: 0 })

const allJobs = computed(() => props.cronData?.jobs || [])
const allTimers = computed(() => props.cronData?.timers || [])

const paginatedJobs = computed(() => {
  if (jobsPageSize.value === 'all') return allJobs.value
  const lim = parseInt(jobsPageSize.value, 10) || 10
  return allJobs.value.slice((jobsPage.value - 1) * lim, jobsPage.value * lim)
})

const paginatedTimers = computed(() => {
  if (timersPageSize.value === 'all') return allTimers.value
  const lim = parseInt(timersPageSize.value, 10) || 10
  return allTimers.value.slice((timersPage.value - 1) * lim, timersPage.value * lim)
})

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: '185px',
}))

function openMenu(job, event) {
  if (menuTarget.value === job) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 140),
    left: Math.max(8, Math.min(rect.right - 185, window.innerWidth - 193)),
  }
  menuTarget.value = job
}

function applyPreset(val) {
  if (val) addForm.value.schedule = val
}

function submitAddCron() {
  const parts = addForm.value.schedule.trim().split(/\s+/)
  if (parts.length !== 5) return
  emit('cron-action', {
    action: 'cron_add',
    params: {
      ident: addForm.value.ident.trim(),
      minute: parts[0], hour: parts[1], dom: parts[2], month: parts[3], dow: parts[4],
      user: addForm.value.user.trim() || 'root',
      command: addForm.value.command.trim(),
    },
  })
  addForm.value = { ident: '', user: 'root', schedule: '0 2 * * *', command: '' }
  showAddForm.value = false
}

async function runCron(job) {
  menuTarget.value = null
  const ok = await confirmAction({
    title: 'Run Cron Job Now',
    message: `Run command immediately as '${job.user || 'root'}':\n\n${job.command}`,
    confirmText: 'Run Now',
    variant: 'warning',
  })
  if (!ok) return
  emit('cron-action', { action: 'cron_run_now', params: { user: job.user || 'root', command: job.command } })
}

async function toggleCron(job) {
  menuTarget.value = null
  const mode = job.is_enabled !== false ? 'disable' : 'enable'
  emit('cron-action', { action: 'cron_toggle', params: { ident: job.ident, mode } })
}

async function deleteCron(job) {
  menuTarget.value = null
  const ok = await confirmAction({
    title: 'Delete Cron Job',
    message: `Delete managed cron job '${job.ident}'?`,
    confirmText: 'Delete',
    variant: 'danger',
  })
  if (!ok) return
  emit('cron-action', { action: 'cron_delete', params: { ident: job.ident } })
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>
