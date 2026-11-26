<template>
  <div
    v-if="isOpen"
    :class="[
      'fixed inset-x-0 bottom-0 z-50 bg-[#070b14]/95 border-t border-cyan-500/40 shadow-2xl backdrop-blur-md flex flex-col font-mono text-xs transition-all',
      isMaximized ? 'top-14' : 'h-80'
    ]"
  >
    <!-- Toolbar -->
    <div class="px-4 py-2 border-b border-gray-800 bg-[#0a101d] flex flex-wrap items-center justify-between gap-2 shrink-0">
      <div class="flex items-center gap-2.5">
        <span class="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 text-[10px] font-bold flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          LIVE
        </span>
        <span class="font-bold text-cyan-300 tracking-wide">Activity Console</span>
        <div class="flex items-center gap-1 ml-2">
          <button
            v-for="lvl in ['ALL', 'ERROR', 'WARN', 'INFO']"
            :key="lvl"
            type="button"
            @click="levelFilter = lvl"
            :class="[
              'px-2 py-0.5 rounded text-[10px] font-bold border transition cursor-pointer',
              levelFilter === lvl
                ? 'bg-cyan-950 text-cyan-300 border-cyan-500/60'
                : 'bg-gray-900/60 text-gray-400 border-gray-800 hover:text-gray-200'
            ]"
          >
            {{ lvl }}
          </button>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Filter host, module, message..."
          class="bg-[#06090f] border border-gray-700 rounded px-2.5 py-1 text-xs text-gray-200 w-44 sm:w-56 focus:border-cyan-500 focus:outline-none"
        />
        <button
          type="button"
          @click="paused = !paused"
          class="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer"
          :title="paused ? 'Resume live updates' : 'Pause live updates'"
        >
          {{ paused ? 'Resume' : 'Pause' }}
        </button>
        <button
          type="button"
          @click="entries = []"
          class="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer"
          title="Clear console"
        >
          Clear
        </button>
        <button
          type="button"
          @click="exportLog"
          class="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer"
          title="Export activity log"
        >
          Export
        </button>
        <button
          type="button"
          @click="isMaximized = !isMaximized"
          class="p-1.5 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer"
          :title="isMaximized ? 'Restore height' : 'Maximize console'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
            <line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
          </svg>
        </button>
        <button
          type="button"
          @click="$emit('close')"
          class="p-1.5 rounded border border-gray-700 bg-gray-900 text-gray-400 hover:text-white cursor-pointer"
          title="Close Activity Console (Esc)"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-y-auto">
      <table class="w-full text-left border-collapse">
        <thead class="sticky top-0 bg-[#0b1220] text-[10px] uppercase text-gray-400 border-b border-gray-800">
          <tr>
            <th class="px-3 py-1.5 w-20">{{ t('th_time') }}</th>
            <th class="px-3 py-1.5 w-20">{{ t('th_level') }}</th>
            <th class="px-3 py-1.5 w-28">{{ t('th_module') }}</th>
            <th class="px-3 py-1.5 w-36">{{ t('th_host') }}</th>
            <th class="px-3 py-1.5">{{ t('th_message_activity') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/50">
          <tr v-if="filteredEntries.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-gray-500">
              No live activity events matching filter.
            </td>
          </tr>
          <tr v-for="item in filteredEntries" :key="item.id" class="hover:bg-cyan-950/15">
            <td class="px-3 py-1.5 text-gray-400 whitespace-nowrap">{{ item.time }}</td>
            <td class="px-3 py-1.5">
              <span :class="levelBadgeClass(item.level)" class="px-1.5 py-0.5 rounded text-[10px] font-bold">
                {{ item.level }}
              </span>
            </td>
            <td class="px-3 py-1.5 text-cyan-300 font-semibold whitespace-nowrap">{{ item.module }}</td>
            <td class="px-3 py-1.5 text-gray-300 whitespace-nowrap">{{ item.host }}</td>
            <td class="px-3 py-1.5 text-gray-200">{{ item.message }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '../../i18n'

const { t } = useI18n()

const props = defineProps({
  isOpen: Boolean,
})

const emit = defineEmits(['close'])

const entries = ref([])
const levelFilter = ref('ALL')
const searchQuery = ref('')
const paused = ref(false)
const isMaximized = ref(false)
let pollTimer = null

const filteredEntries = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return [...entries.value].reverse().filter((item) => {
    if (levelFilter.value !== 'ALL' && item.level !== levelFilter.value) return false
    if (!q) return true
    return (
      (item.host || '').toLowerCase().includes(q) ||
      (item.module || '').toLowerCase().includes(q) ||
      (item.message || '').toLowerCase().includes(q)
    )
  })
})

function levelBadgeClass(lvl) {
  if (lvl === 'ERROR' || lvl === 'CRITICAL') return 'bg-rose-950 text-rose-300 border border-rose-700/60'
  if (lvl === 'WARN' || lvl === 'WARNING') return 'bg-amber-950 text-amber-300 border border-amber-700/60'
  return 'bg-cyan-950 text-cyan-300 border border-cyan-700/60'
}

async function fetchRecent() {
  if (paused.value) return
  const token = localStorage.getItem('pantau_token')
  if (!token) return
  try {
    const res = await fetch('/api/activity/recent?limit=100', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      entries.value = data.items || []
    }
  } catch (_) {}
}

function exportLog() {
  const lines = filteredEntries.value.map((e) => `[${e.timestamp || e.time}] [${e.level}] [${e.module}] [${e.host}] ${e.message}`)
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pantau-activity-${new Date().toISOString().slice(0, 19)}.log`
  a.click()
  URL.revokeObjectURL(url)
}

function onEsc(e) {
  if (props.isOpen && e.key === 'Escape') emit('close')
}

watch(() => props.isOpen, (open) => {
  if (open) {
    fetchRecent()
    pollTimer = setInterval(fetchRecent, 3000)
    window.addEventListener('keydown', onEsc)
  } else {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    window.removeEventListener('keydown', onEsc)
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('keydown', onEsc)
})
</script>
