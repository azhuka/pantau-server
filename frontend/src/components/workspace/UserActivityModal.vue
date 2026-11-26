<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-[100020] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono text-xs"
    >
      <div class="bg-[#0b1220] border border-cyan-500/40 rounded-xl w-full max-w-5xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        <!-- Header -->
        <div class="px-5 py-3 border-b border-gray-800 bg-[#070c18] flex items-center justify-between flex-wrap gap-2 shrink-0">
          <div>
            <h3 class="text-sm font-bold text-cyan-300">User Activity: {{ username }}</h3>
            <p class="text-[11px] text-gray-400">Active sessions, login audit, sudo usage, and shell command history</p>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <template v-if="!isViewer && isOnline">
              <button
                v-for="s in (account?.sessions || []).filter(x => x.tty)"
                :key="s.tty"
                type="button"
                @click="$emit('terminate-ssh', username, s.tty)"
                class="px-2.5 py-1 rounded border border-rose-700 bg-rose-950/70 text-rose-300 hover:bg-rose-800 hover:text-white font-bold cursor-pointer transition"
                :title="`Terminate active session ${s.tty}`"
              >
                Terminate {{ s.tty }}
              </button>
            </template>
            <button
              type="button"
              @click="fetchActivity"
              :disabled="loading"
              class="px-2.5 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer disabled:opacity-40"
            >
              {{ loading ? 'Loading...' : 'Refresh' }}
            </button>
            <button
              type="button"
              @click="exportCsv"
              :disabled="filteredRows.length === 0"
              class="px-2.5 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer disabled:opacity-40"
            >
              Export CSV
            </button>
            <button type="button" @click="$emit('close')" class="p-1 text-gray-400 hover:text-white cursor-pointer" title="Close">
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 4 Account Summary Cards -->
        <div v-if="account" class="grid grid-cols-2 lg:grid-cols-4 gap-2.5 px-5 py-3 border-b border-gray-800/80 bg-[#080e1a] shrink-0">
          <div class="p-2.5 rounded-lg bg-[#060a14] border border-gray-800/80">
            <div class="text-[10px] uppercase text-gray-400 font-bold">UID / GID</div>
            <div class="text-sm font-bold text-gray-100 mt-0.5">{{ account.uid ?? '-' }} / {{ account.gid ?? '-' }}</div>
            <div class="flex gap-1 mt-1">
              <span v-if="account.is_sudo" class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">Sudoer</span>
              <span class="px-1.5 py-0.2 rounded text-[9px] font-bold" :class="account.is_system ? 'bg-gray-800 text-gray-400' : 'bg-emerald-950 text-emerald-300'">{{ account.is_system ? 'System' : 'Regular' }}</span>
            </div>
          </div>
          <div class="p-2.5 rounded-lg bg-[#060a14] border border-gray-800/80">
            <div class="text-[10px] uppercase text-gray-400 font-bold">Primary &amp; Groups</div>
            <div class="text-xs font-bold text-gray-100 mt-0.5 truncate">{{ account.group || '-' }}</div>
            <div class="text-[10px] text-gray-400 truncate mt-0.5" :title="(account.groups || []).join(', ')">
              {{ (account.groups || []).length ? account.groups.join(', ') : 'No secondary groups' }}
            </div>
          </div>
          <div class="p-2.5 rounded-lg bg-[#060a14] border border-gray-800/80">
            <div class="text-[10px] uppercase text-gray-400 font-bold">Home &amp; Shell</div>
            <div class="text-[11px] font-semibold text-gray-200 mt-0.5 truncate" :title="account.home">{{ account.home || '-' }}</div>
            <div class="text-[11px] text-cyan-400 truncate mt-0.5">{{ account.shell || '-' }}</div>
          </div>
          <div class="p-2.5 rounded-lg bg-[#060a14] border border-gray-800/80">
            <div class="text-[10px] uppercase text-gray-400 font-bold">Sessions &amp; Last Login</div>
            <div class="text-xs font-bold mt-0.5" :class="(account.sessions || []).length ? 'text-emerald-400' : 'text-gray-300'">
              {{ (account.sessions || []).length }} Active
            </div>
            <div class="text-[10px] text-gray-400 truncate mt-0.5" :title="account.last_login">{{ account.last_login || 'No login history' }}</div>
          </div>
        </div>

        <!-- Interactive Category Chips -->
        <div v-if="rows.length > 0" class="px-5 py-2 border-b border-gray-800/80 bg-[#070c18] flex items-center gap-1.5 flex-wrap shrink-0">
          <button
            v-for="chip in categoryChips"
            :key="chip.id"
            type="button"
            @click="typeFilter = typeFilter === chip.id ? '' : chip.id"
            class="px-2 py-0.5 rounded text-[10px] font-bold border transition cursor-pointer"
            :class="typeFilter === chip.id ? 'ring-1 ring-cyan-400 ' + chip.cls : chip.cls + ' opacity-85 hover:opacity-100'"
          >
            {{ chip.label }}: {{ chip.count }}
          </button>
          <button v-if="typeFilter" type="button" @click="typeFilter = ''" class="ml-auto px-2 py-0.5 rounded text-[10px] text-gray-300 hover:text-white bg-gray-800 cursor-pointer">
            Reset Filter
          </button>
        </div>

        <!-- Search & Type Filter Bar -->
        <div class="px-5 py-2 border-b border-gray-800 bg-[#080e1a] flex items-center justify-between gap-3 flex-wrap shrink-0">
          <div class="flex items-center gap-2 flex-wrap">
            <select v-model="typeFilter" class="bg-[#06090f] border border-gray-700 rounded px-2.5 py-1 text-xs text-gray-200 outline-none">
              <option value="">All Event Types</option>
              <option value="aktif">Active Session</option>
              <option value="login">Login</option>
              <option value="selesai">Logout / Completed</option>
              <option value="shell">Shell Command</option>
              <option value="sudo">Sudo Execution</option>
              <option value="proses">Active Process</option>
              <option value="cron">Cron Task</option>
              <option value="sistem">System Journal</option>
              <option value="gagal">Failed Login</option>
              <option value="sudo_gagal">Failed Sudo</option>
            </select>
            <input
              v-model="search"
              type="search"
              placeholder="Filter command, IP, PWD, TTY..."
              class="bg-[#06090f] border border-gray-700 rounded px-3 py-1 text-xs text-gray-200 w-64 focus:border-cyan-500 focus:outline-none"
            />
          </div>
          <span class="text-[11px] text-gray-400">{{ filteredRows.length }} events</span>
        </div>

        <!-- Table -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="errorMsg" class="m-4 p-3 rounded bg-rose-950/60 border border-rose-700/60 text-rose-200">{{ errorMsg }}</div>
          <div v-else-if="loading" class="py-12 text-center text-gray-400">Querying user activity from remote agent...</div>
          <table v-else class="w-full text-left border-collapse">
            <thead class="sticky top-0 bg-[#0b1220] text-[10px] uppercase text-gray-400 border-b border-gray-800">
              <tr>
                <th class="px-3 py-2">{{ t('th_time') }}</th>
                <th class="px-3 py-2">{{ t('th_type') }}</th>
                <th class="px-3 py-2">{{ t('th_tty') }}</th>
                <th class="px-3 py-2">{{ t('th_source_ip') }}</th>
                <th class="px-3 py-2">{{ t('th_pwd') }}</th>
                <th class="px-3 py-2">{{ t('th_command_details') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-800/50">
              <tr v-if="paginatedRows.length === 0">
                <td colspan="6" class="px-4 py-10 text-center text-gray-500">No user activity records found.</td>
              </tr>
              <tr v-for="(r, idx) in paginatedRows" :key="idx" class="hover:bg-cyan-950/15">
                <td class="px-3 py-1.5 text-gray-400 whitespace-nowrap">{{ r.ts || r.time || r.timestamp || '-' }}</td>
                <td class="px-3 py-1.5 whitespace-nowrap">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-bold border" :class="typeBadgeClass(r.type)">
                    {{ formatTypeLabel(r.type) }}
                  </span>
                </td>
                <td class="px-3 py-1.5 text-gray-300 whitespace-nowrap">{{ r.tty || r.terminal || '-' }}</td>
                <td class="px-3 py-1.5 text-gray-300 whitespace-nowrap">{{ r.from || r.ip || r.source || '-' }}</td>
                <td class="px-3 py-1.5 text-gray-400 truncate max-w-[140px]" :title="r.pwd || ''">{{ r.pwd || '-' }}</td>
                <td class="px-3 py-1.5 text-gray-200 break-all">{{ r.command || r.cmd || r.method || r.detail || r.message || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="px-4 py-2 border-t border-gray-800 bg-[#070c18] shrink-0">
          <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredRows.length" unitLabel="events" :pageSizeOptions="[10, 25, 50, 100, 'all']" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '../../i18n'
import NocTablePagination from '../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  serverId: Number,
  username: { type: String, default: '' },
  account: { type: Object, default: null },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'terminate-ssh'])

const loading = ref(false)
const errorMsg = ref('')
const rows = ref([])
const search = ref('')
const typeFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(25)

watch([search, typeFilter], () => { currentPage.value = 1 })

const categoryChips = computed(() => {
  const counts = { aktif: 0, login: 0, selesai: 0, shell: 0, sudo: 0, proses: 0, cron: 0, sistem: 0, gagal: 0, sudo_gagal: 0 }
  for (const r of rows.value) {
    const tp = r.type === 'sukses' ? 'login' : r.type
    if (tp in counts) counts[tp]++
  }
  const defs = [
    { id: 'aktif', label: 'Active', cls: 'bg-emerald-950 text-emerald-300 border-emerald-700' },
    { id: 'login', label: 'Login', cls: 'bg-cyan-950 text-cyan-300 border-cyan-700' },
    { id: 'selesai', label: 'Completed', cls: 'bg-gray-800 text-gray-300 border-gray-700' },
    { id: 'shell', label: 'Shell', cls: 'bg-sky-950 text-sky-300 border-sky-700' },
    { id: 'sudo', label: 'Sudo', cls: 'bg-amber-950 text-amber-300 border-amber-700' },
    { id: 'proses', label: 'Processes', cls: 'bg-indigo-950 text-indigo-300 border-indigo-700' },
    { id: 'cron', label: 'Cron', cls: 'bg-purple-950 text-purple-300 border-purple-700' },
    { id: 'sistem', label: 'System', cls: 'bg-blue-950 text-blue-300 border-blue-700' },
    { id: 'gagal', label: 'Failed Login', cls: 'bg-rose-950 text-rose-300 border-rose-700' },
    { id: 'sudo_gagal', label: 'Failed Sudo', cls: 'bg-rose-950 text-rose-300 border-rose-700' },
  ]
  return defs.map(d => ({ ...d, count: counts[d.id] })).filter(d => d.count > 0)
})

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    const tp = r.type === 'sukses' ? 'login' : r.type
    if (typeFilter.value && tp !== typeFilter.value) return false
    if (!q) return true
    return `${r.ts || r.time || ''} ${r.type || ''} ${r.tty || ''} ${r.from || r.ip || ''} ${r.pwd || ''} ${r.command || r.cmd || r.method || r.detail || ''}`.toLowerCase().includes(q)
  })
})

const paginatedRows = computed(() => {
  if (pageSize.value === 'all') return filteredRows.value
  const lim = parseInt(pageSize.value, 10) || 25
  return filteredRows.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})

function formatTypeLabel(tp) {
  const map = {
    aktif: 'ACTIVE', login: 'LOGIN', sukses: 'LOGIN', selesai: 'LOGOUT',
    shell: 'SHELL', sudo: 'SUDO', proses: 'PROCESS', cron: 'CRON',
    sistem: 'SYSTEM', gagal: 'FAILED LOGIN', sudo_gagal: 'FAILED SUDO',
  }
  return map[tp] || String(tp || '-').toUpperCase()
}

function typeBadgeClass(tp) {
  if (tp === 'aktif') return 'bg-emerald-950 text-emerald-300 border-emerald-700'
  if (tp === 'login' || tp === 'sukses' || tp === 'shell') return 'bg-cyan-950 text-cyan-300 border-cyan-700'
  if (tp === 'sudo' || tp === 'polkit') return 'bg-amber-950 text-amber-300 border-amber-700'
  if (tp === 'gagal' || tp === 'sudo_gagal') return 'bg-rose-950 text-rose-300 border-rose-700'
  if (tp === 'cron') return 'bg-purple-950 text-purple-300 border-purple-700'
  return 'bg-gray-800 text-gray-300 border-gray-700'
}

async function fetchActivity() {
  if (!props.serverId || !props.username) return
  loading.value = true
  errorMsg.value = ''
  rows.value = []
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/logs/request', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ server_id: props.serverId, unit: 'USER_ACTIVITY', lines: 200, detail: props.username }),
    })
    const created = await res.json()
    if (!res.ok) throw new Error(created.detail || 'Failed to request user activity')
    const rid = created.request_id || created.id

    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 700))
      const poll = await fetch(`/api/logs/request/${rid}`, { headers: { Authorization: `Bearer ${token}` } })
      const pdata = await poll.json()
      if (pdata.status === 'success') {
        const parsed = typeof pdata.result === 'string' ? JSON.parse(pdata.result || '{}') : (pdata.result || {})
        rows.value = Array.isArray(parsed) ? parsed : (parsed.logins || parsed.events || parsed.entries || parsed.logs || [])
        return
      }
      if (pdata.status === 'failed') throw new Error(pdata.result || 'Agent failed to collect user activity')
    }
    throw new Error('Timed out waiting for agent user activity response')
  } catch (e) {
    errorMsg.value = e.message || 'Failed to load user activity'
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = ['Time,Type,TTY,Source IP,PWD,Command']
  for (const r of filteredRows.value) {
    lines.push([r.ts || r.time || r.timestamp, formatTypeLabel(r.type), r.tty || r.terminal, r.from || r.ip || r.source, r.pwd, r.command || r.cmd || r.method || r.detail].map(esc).join(','))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `user-activity-${props.username}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function onEsc(e) { if (props.isOpen && e.key === 'Escape') emit('close') }
watch(() => props.isOpen, (open) => {
  if (open) { typeFilter.value = ''; search.value = ''; fetchActivity(); window.addEventListener('keydown', onEsc) }
  else { window.removeEventListener('keydown', onEsc) }
})
onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>
