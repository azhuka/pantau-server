<template>
  <div v-if="isOpen" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="hud-tactical-card rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200 font-mono">
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <h3 class="text-sm font-bold text-cyan-300 uppercase tracking-wider">
          {{ revealedKey ? 'Agent API Key & Installation' : 'Register New Asset' }}
        </h3>
        <button type="button" @click="closeModal" class="text-gray-400 hover:text-white cursor-pointer p-1" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- Step 1: Registration Form -->
      <form v-if="!revealedKey" @submit.prevent="submit" class="space-y-3 text-xs">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Hostname</label>
            <input v-model="form.hostname" required placeholder="e.g. web-prod-01" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">IP Address (Optional)</label>
            <input v-model="form.ip_address" placeholder="e.g. 172.30.1.50" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Asset Group</label>
            <input v-model="form.group_name" placeholder="e.g. Core Infrastructure" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">Environment</label>
            <select v-model="form.tier" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
              <option :value="1">Production</option>
              <option :value="2">Non-Production</option>
            </select>
          </div>
        </div>

        <label class="flex items-center gap-2 text-gray-300 pt-1 cursor-pointer">
          <input type="checkbox" v-model="form.is_proxmox_ha" class="accent-cyan-500" />
          <span>Protected by Proxmox HA (Disable remote Power Off)</span>
        </label>

        <div class="flex justify-end gap-2 pt-3 border-t border-gray-800">
          <button type="button" @click="closeModal" class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
          <button type="submit" :disabled="saving" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer disabled:opacity-50">
            {{ saving ? 'Registering...' : 'Register & Generate Key' }}
          </button>
        </div>
      </form>

      <!-- Step 2: Key Reveal -->
      <div v-else class="space-y-3 text-xs">
        <div class="p-2.5 rounded bg-amber-950/50 border border-amber-700/60 text-amber-200">
          Save this API key now. For security reasons, it will not be displayed again.
        </div>

        <div>
          <label class="block text-gray-400 font-bold mb-1">Agent API Key ({{ revealedHostname }})</label>
          <div class="flex gap-2">
            <input :value="revealedKey" readonly class="flex-1 bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-cyan-300 select-all" />
            <button type="button" @click="copyText(revealedKey)" class="px-3 py-1.5 rounded bg-cyan-950 hover:bg-cyan-800 text-cyan-300 border border-cyan-700 font-bold cursor-pointer">Copy</button>
          </div>
        </div>

        <div>
          <label class="block text-gray-400 font-bold mb-1">Agent Configuration Hint</label>
          <div class="p-2.5 rounded bg-[#070c18] border border-gray-800 text-gray-300 break-all select-all">
            SERVER_URL="{{ originUrl }}" API_KEY="{{ revealedKey }}"
          </div>
        </div>

        <div class="flex justify-end pt-2 border-t border-gray-800">
          <button type="button" @click="closeModal" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { apiFetch } from '../../../utils/api'
import { useToast } from '../../../utils/useToast'

defineProps({ isOpen: { type: Boolean, default: false } })
const emit = defineEmits(['close', 'created'])
const toast = useToast()

const saving = ref(false)
const revealedKey = ref('')
const revealedHostname = ref('')
const form = ref({ hostname: '', ip_address: '', group_name: '', tier: 1, is_proxmox_ha: false })
const originUrl = computed(() => window.location.origin)

async function submit() {
  saving.value = true
  try {
    const res = await apiFetch('/api/servers', { method: 'POST', body: JSON.stringify(form.value) })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to register asset')
    revealedKey.value = data.api_key
    revealedHostname.value = data.hostname
    toast.success(data.message)
    emit('created')
  } catch (err) {
    toast.error(err.message)
  } finally {
    saving.value = false
  }
}

function copyText(txt) {
  navigator.clipboard?.writeText(txt)
  toast.success('Copied to clipboard')
}

function closeModal() {
  revealedKey.value = ''
  revealedHostname.value = ''
  form.value = { hostname: '', ip_address: '', group_name: '', tier: 1, is_proxmox_ha: false }
  emit('close')
}
</script>
