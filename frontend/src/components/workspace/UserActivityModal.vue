<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[70] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-mono text-xs"
    @click.self="$emit('close')"
  >
    <div class="bg-[#0b1220] border border-cyan-500/40 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
      <div class="px-5 py-3 border-b border-gray-800 bg-[#070c18] flex items-center justify-between shrink-0">
        <div>
          <h3 class="text-sm font-bold text-cyan-300">User Activity: {{ username }}</h3>
          <p class="text-[11px] text-gray-400">Login sessions, sudo usage, and shell command history</p>
        </div>
        <div class="flex items-center gap-2">
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

      <div class="px-5 py-2.5 border-b border-gray-800 bg-[#080e1a] flex items-center justify-between gap-3 shrink-0">
        <input
          v-model="search"
          type="search"
          placeholder="Filter command, IP, TTY, type..."
          class="bg-[#06090f] border border-gray-700 rounded px-3 py-1 text-xs text-gray-200 w-72 focus:border-cyan-500 focus:outline-none"
        />
        <span class="text-[11px] text-gray-400">{{ filteredRows.length }} events</span>
      </div>

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
              <th class="px-3 py-2">{{ t('th_command_details') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr v-if="filteredRows.length === 0">
              <td colspan="5" class="px-4 py-10 text-center text-gray-500">No user activity records found.</td>
            </tr>
            <tr v-for="(r, idx) in filteredRows" :key="idx" class="hover:bg-cyan-950/15">
              <td class="px-3 py-1.5 text-gray-400 whitespace-nowrap">{{ r.ts || r.time || r.timestamp || '-' }}</td>
              <td class="px-3 py-1.5 text-cyan-300 font-semibold whitespace-nowrap uppercase">{{ r.type || r.category || '-' }}</td>
              <td class="px-3 py-1.5 text-gray-300 whitespace-nowrap">{{ r.tty || r.terminal || '-' }}</td>
              <td class="px-3 py-1.5 text-gray-300 whitespace-nowrap">{{ r.from || r.ip || r.source || '-' }}</td>
              <td class="px-3 py-1.5 text-gray-200 break-all">{{ r.command || r.cmd || r.method || r.detail || r.message || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '../../i18n'

const { t } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  serverId: Number,
  username: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const errorMsg = ref('')
const rows = ref([])
const search = ref('')

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((r) =>
    `${r.ts || r.time || ''} ${r.type || ''} ${r.tty || ''} ${r.from || r.ip || ''} ${r.command || r.cmd || r.method || r.detail || ''}`.toLowerCase().includes(q)
  )
})

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
      if (pdata.status === 'failed') {
        throw new Error(pdata.result || 'Agent failed to collect user activity')
      }
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
  const lines = ['Time,Type,TTY,Source IP,Command']
  for (const r of filteredRows.value) {
    lines.push([r.ts || r.time || r.timestamp, r.type || r.category, r.tty || r.terminal, r.from || r.ip || r.source, r.command || r.cmd || r.method || r.detail].map(esc).join(','))
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `user-activity-${props.username}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function onEsc(e) {
  if (props.isOpen && e.key === 'Escape') emit('close')
}

watch(() => props.isOpen, (open) => {
  if (open) {
    search.value = ''
    fetchActivity()
    window.addEventListener('keydown', onEsc)
  } else {
    window.removeEventListener('keydown', onEsc)
  }
})

onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>
