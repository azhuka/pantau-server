<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[20000] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-mono text-xs"
  >
    <div class="bg-[#0b1220] border border-cyan-500/40 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
      <div class="px-5 py-3 border-b border-gray-800 bg-[#070c18] flex items-center justify-between shrink-0">
        <div class="flex items-center gap-2.5">
          <h3 class="text-sm font-bold text-cyan-300">Storage Analysis</h3>
          <span class="text-[11px] text-gray-400">Mount: {{ mountPath }}</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="loadTriage"
            :disabled="loading"
            class="px-2.5 py-1 rounded border border-gray-700 bg-gray-900 text-gray-300 hover:text-white cursor-pointer disabled:opacity-40"
          >
            {{ loading ? 'Scanning...' : 'Refresh' }}
          </button>
          <button type="button" @click="$emit('close')" class="p-1 text-gray-400 hover:text-white cursor-pointer" title="Close">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="px-5 py-2 border-b border-gray-800 bg-[#080e1a] flex items-center gap-2 shrink-0">
        <button
          v-for="tab in TABS"
          :key="tab.id"
          type="button"
          @click="activeTab = tab.id"
          :class="[
            'px-3 py-1.5 rounded border font-bold cursor-pointer transition',
            activeTab === tab.id ? 'bg-cyan-950 text-cyan-300 border-cyan-500/60' : 'bg-gray-900/60 text-gray-400 border-gray-800 hover:text-white'
          ]"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="p-5 overflow-y-auto flex-1 space-y-3">
        <div v-if="errorMsg" class="p-3 rounded bg-rose-950/60 border border-rose-700/60 text-rose-200">{{ errorMsg }}</div>
        <div v-else-if="loading" class="py-12 text-center text-gray-400">Analyzing remote storage on host...</div>

        <template v-else>
          <div v-if="activeTab === 'hogs'" class="space-y-1.5">
            <div v-if="hogs.length === 0" class="py-8 text-center text-gray-500">No large files found.</div>
            <div v-for="(item, idx) in hogs" :key="idx" class="p-2.5 rounded bg-gray-900/60 border border-gray-800 flex items-center justify-between gap-3">
              <span class="text-gray-200 truncate">{{ item.path || item.name }}</span>
              <div class="flex items-center gap-2 shrink-0">
                <span class="text-amber-300 font-bold">{{ item.size_human || item.size }}</span>
                <button
                  v-if="String(item.path || '').startsWith('/var/log/')"
                  type="button"
                  @click="truncateLog(item.path)"
                  class="px-2 py-0.5 rounded bg-rose-950/80 border border-rose-700 text-rose-200 hover:bg-rose-800 cursor-pointer"
                >
                  Truncate
                </button>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'ghosts'" class="space-y-1.5">
            <div v-if="ghosts.length === 0" class="py-8 text-center text-gray-500">No deleted open file handles detected.</div>
            <div v-for="(g, idx) in ghosts" :key="idx" class="p-2.5 rounded bg-gray-900/60 border border-gray-800 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="text-gray-200 truncate">{{ g.path || g.name }}</div>
                <div class="text-[11px] text-gray-400">PID {{ g.pid }} ({{ g.proc || g.command }})</div>
              </div>
              <span class="text-amber-300 font-bold shrink-0">{{ g.size_human || g.size }}</span>
            </div>
          </div>

          <div v-else class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div v-for="rc in RECLAIM_TARGETS" :key="rc.id" class="p-4 rounded-lg bg-gray-900/60 border border-gray-800 flex flex-col justify-between gap-3">
              <div>
                <div class="font-bold text-gray-100">{{ rc.title }}</div>
                <div class="text-[11px] text-gray-400 mt-1">{{ rc.desc }}</div>
              </div>
              <button
                type="button"
                @click="reclaimTarget(rc.id)"
                :disabled="reclaiming === rc.id"
                class="px-3 py-1.5 rounded bg-cyan-900/70 hover:bg-cyan-700 text-cyan-100 border border-cyan-600/50 font-bold cursor-pointer disabled:opacity-40"
              >
                {{ reclaiming === rc.id ? 'Reclaiming...' : 'Reclaim Space' }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { useToast } from '../../utils/useToast'

const props = defineProps({
  isOpen: Boolean,
  serverId: Number,
  mountPath: { type: String, default: '/' },
})
const emit = defineEmits(['close', 'updated'])
const toast = useToast()

const TABS = [
  { id: 'hogs', label: 'Large Files & Logs' },
  { id: 'ghosts', label: 'Deleted Open Files' },
  { id: 'reclaim', label: 'Reclaim Space' },
]

const RECLAIM_TARGETS = [
  { id: 'journal', title: 'Systemd Journal', desc: 'Vacuum old systemd journal logs' },
  { id: 'apt_cache', title: 'APT Package Cache', desc: 'Clean cached .deb archives' },
  { id: 'rotated_logs', title: 'Rotated Logs', desc: 'Remove old compressed .gz/.1 logs' },
]

const activeTab = ref('hogs')
const loading = ref(false)
const reclaiming = ref('')
const errorMsg = ref('')
const hogs = ref([])
const ghosts = ref([])

async function loadTriage() {
  if (!props.serverId) return
  loading.value = true
  errorMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/files/storage-triage?mount=${encodeURIComponent(props.mountPath || '/')}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Storage analysis failed')
    hogs.value = data.hogs || data.large_files || []
    ghosts.value = data.ghosts || data.deleted_open || []
  } catch (e) {
    errorMsg.value = e.message || 'Storage analysis failed'
  } finally {
    loading.value = false
  }
}

async function truncateLog(path) {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/files/truncate-log`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Truncate failed')
    toast.success(`Truncated ${path}`)
    await loadTriage()
    emit('updated')
  } catch (e) {
    toast.error(e.message)
  }
}

async function reclaimTarget(target) {
  reclaiming.value = target
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/files/storage-reclaim`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ target }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Reclaim failed')
    toast.success(data.message || `Reclaimed ${target}`)
    await loadTriage()
    emit('updated')
  } catch (e) {
    toast.error(e.message)
  } finally {
    reclaiming.value = ''
  }
}

function onEsc(e) {
  if (props.isOpen && e.key === 'Escape') emit('close')
}

watch(() => props.isOpen, (open) => {
  if (open) {
    activeTab.value = 'hogs'
    loadTriage()
    window.addEventListener('keydown', onEsc)
  } else {
    window.removeEventListener('keydown', onEsc)
  }
})

onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>
