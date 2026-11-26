<template>
  <div class="space-y-5 font-mono">
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between gap-3 flex-wrap shadow-lg">
      <div>
        <h2 class="text-sm font-extrabold text-cyan-300 tracking-wider uppercase">Scheduled Maintenance Windows</h2>
        <p class="text-[11px] text-gray-400 mt-0.5">Centralized maintenance schedules to suppress alerts across single, group, or all assets.</p>
      </div>
      <button v-if="canManage" @click="showModal = true" class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition cursor-pointer">
        + Schedule Maintenance
      </button>
    </div>

    <div class="grid grid-cols-3 gap-3">
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-amber-400">Active Now</div><div class="text-2xl font-extrabold text-amber-300 mt-1">{{ summary.active }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-cyan-400">Scheduled</div><div class="text-2xl font-extrabold text-cyan-300 mt-1">{{ summary.scheduled }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-emerald-400">Completed</div><div class="text-2xl font-extrabold text-emerald-300 mt-1">{{ summary.completed }}</div></div>
    </div>

    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-xl">
      <div v-if="windows.length === 0" class="p-8 text-center text-xs text-gray-400">
        No maintenance windows scheduled.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="border-b border-cyan-500/20 text-gray-400 bg-[#070c18]/80 font-bold">
            <tr>
              <th class="py-2.5 px-3">{{ t('th_status') }}</th>
              <th class="py-2.5 px-3">{{ t('th_title') }}</th>
              <th class="py-2.5 px-3">{{ t('th_target_scope') }}</th>
              <th class="py-2.5 px-3">{{ t('th_schedule') }}</th>
              <th class="py-2.5 px-3">{{ t('th_start_time') }}</th>
              <th class="py-2.5 px-3">{{ t('th_end_time') }}</th>
              <th v-if="canManage" class="py-2.5 px-3 text-right">{{ t('th_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr v-for="w in paginatedWindows" :key="w.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-3">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border" :class="winStatusClass(w.status)">{{ w.status }}</span>
              </td>
              <td class="py-2.5 px-3 font-bold text-gray-100">{{ w.title }}</td>
              <td class="py-2.5 px-3 text-cyan-300">{{ w.target_label }}</td>
              <td class="py-2.5 px-3 uppercase text-gray-300">{{ w.schedule_type }}</td>
              <td class="py-2.5 px-3 text-gray-400">{{ formatIncidentTime(w.start_time) }}</td>
              <td class="py-2.5 px-3 text-gray-400">{{ formatIncidentTime(w.end_time) }}</td>
              <td v-if="canManage" class="py-2.5 px-3 text-right">
                <div class="inline-flex items-center gap-1">
                  <button v-if="w.status === 'active'" @click="completeWindow(w)" class="w-[26px] h-[26px] flex items-center justify-center rounded bg-emerald-950/80 hover:bg-emerald-800 text-emerald-300 border border-emerald-700/60 cursor-pointer" title="Mark Completed">
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                  </button>
                  <button @click="deleteWindow(w)" class="w-[26px] h-[26px] flex items-center justify-center rounded bg-rose-950/80 hover:bg-rose-800 text-rose-300 border border-rose-700/60 cursor-pointer" title="Delete Maintenance Window">
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="windows.length" unitLabel="windows" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>

    <!-- Schedule Modal -->
    <div v-if="showModal" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4" @click.self="showModal = false">
      <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200">
        <div class="flex items-center justify-between border-b border-gray-800 pb-2">
          <h3 class="text-sm font-bold text-cyan-300 uppercase">Schedule Maintenance Window</h3>
          <button @click="showModal = false" class="text-gray-400 hover:text-white cursor-pointer" title="Close">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <form @submit.prevent="createWindow" class="space-y-3 text-xs">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Title</label>
            <input v-model="form.title" required placeholder="e.g. Monthly Kernel Patching" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">Scope</label>
              <select v-model="form.scope_type" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100">
                <option value="all">All Assets</option>
                <option value="single">Single Asset</option>
              </select>
            </div>
            <div v-if="form.scope_type === 'single'">
              <label class="block text-gray-400 font-bold mb-1">Asset</label>
              <select v-model="form.server_id" required class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100">
                <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.hostname }}</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">Start (UTC)</label>
              <input v-model="form.start_time" type="datetime-local" required class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
            </div>
            <div>
              <label class="block text-gray-400 font-bold mb-1">End (UTC)</label>
              <input v-model="form.end_time" type="datetime-local" required class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-3 border-t border-gray-800">
            <button type="button" @click="showModal = false" class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 cursor-pointer">Cancel</button>
            <button type="submit" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer">Save</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '../../i18n'
import { apiFetch } from '../../utils/api'
import { formatIncidentTime } from '../../utils/formatters'
import { useToast } from '../../utils/useToast'
import NocTablePagination from '../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null },
})
const toast = useToast()
const windows = ref([])
const summary = ref({ active: 0, scheduled: 0, completed: 0 })
const currentPage = ref(1)
const pageSize = ref(10)
const showModal = ref(false)
const form = ref({ title: '', scope_type: 'all', server_id: '', start_time: '', end_time: '' })

const canManage = computed(() => Boolean(props.currentUser?.is_master_admin || props.currentUser?.permissions?.can_manage_servers || props.currentUser?.permissions?.can_server_control))
const paginatedWindows = computed(() => {
  if (pageSize.value === 'all') return windows.value
  const lim = parseInt(pageSize.value, 10) || 10
  return windows.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})

function winStatusClass(st) {
  if (st === 'active') return 'bg-amber-950/80 text-amber-300 border-amber-600/60'
  if (st === 'scheduled') return 'bg-cyan-950/80 text-cyan-300 border-cyan-600/60'
  return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60'
}

async function fetchWindows() {
  const res = await apiFetch('/api/maintenance-windows')
  if (res.ok) {
    const data = await res.json()
    windows.value = data.windows || []
    summary.value = data.summary || summary.value
  }
}

async function createWindow() {
  const res = await apiFetch('/api/maintenance-windows', { method: 'POST', body: JSON.stringify(form.value) })
  const data = await res.json()
  if (res.ok) {
    toast.success(data.message || 'Maintenance scheduled')
    showModal.value = false
    form.value = { title: '', scope_type: 'all', server_id: '', start_time: '', end_time: '' }
    fetchWindows()
  } else {
    toast.error(data.detail || 'Failed to schedule maintenance')
  }
}

async function completeWindow(w) {
  const res = await apiFetch(`/api/maintenance-windows/${w.id}/complete`, { method: 'POST' })
  if (res.ok) { toast.success((await res.json()).message); fetchWindows() }
}

async function deleteWindow(w) {
  const res = await apiFetch(`/api/maintenance-windows/${w.id}`, { method: 'DELETE' })
  if (res.ok) { toast.success((await res.json()).message); fetchWindows() }
}

onMounted(fetchWindows)
</script>
