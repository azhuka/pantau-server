<template>
  <div v-if="isOpen" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4" @keydown.esc="closeModal">
    <div class="hud-tactical-card rounded-xl max-w-2xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200 font-mono overflow-hidden">
      <div class="flex items-center justify-between border-b border-gray-800 px-5 py-3.5 shrink-0">
        <h3 class="text-sm font-bold text-cyan-300 uppercase tracking-wider">
          {{ revealedKey ? `API Key — ${revealedHostname}` : 'Register New Server Asset' }}
        </h3>
        <button type="button" @click="closeModal" class="text-gray-400 hover:text-white cursor-pointer p-1" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- Step 1: Registration Form -->
      <form v-if="!revealedKey" @submit.prevent="submit" class="flex flex-col flex-1 min-h-0">
        <div class="p-5 space-y-3.5 text-xs overflow-y-auto flex-1">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">Hostname *</label>
              <input v-model="form.hostname" required placeholder="e.g. web-prod-01" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-gray-400 font-bold mb-1">IP Address</label>
              <input v-model="form.ip_address" placeholder="e.g. 172.30.1.50" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">Asset Group</label>
              <input v-model="form.group_name" placeholder="e.g. Production, Web, Core" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
              <div v-if="existingGroups.length" class="flex flex-wrap items-center gap-1.5 mt-1.5">
                <button
                  v-for="grp in existingGroups"
                  :key="grp"
                  type="button"
                  @click="form.group_name = grp"
                  class="px-2 py-0.5 rounded-full text-[10px] border transition cursor-pointer"
                  :class="form.group_name === grp ? 'bg-cyan-950 border-cyan-500 text-cyan-200 font-bold' : 'bg-[#070c18] border-gray-700 text-gray-400 hover:text-gray-200'"
                >
                  {{ grp }}
                </button>
                <button v-if="form.group_name" type="button" @click="form.group_name = ''" class="text-[10px] text-gray-500 hover:text-gray-300 cursor-pointer">Clear</button>
              </div>
            </div>
            <div>
              <label class="block text-gray-400 font-bold mb-1">Tags (Optional)</label>
              <input v-model="form.tags" placeholder="e.g. web, nginx, primary" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
            </div>
          </div>

          <div>
            <label class="block text-gray-400 font-bold mb-1">Description / Notes</label>
            <textarea v-model="form.notes" rows="2" placeholder="Optional server role, backup schedule, or PIC contact..." class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none"></textarea>
          </div>

          <!-- Operational Policies -->
          <div class="p-3 rounded-lg border border-gray-800 bg-[#070c18]/60 space-y-3">
            <div class="text-[11px] font-bold uppercase text-cyan-300 tracking-wider">Operational Policies</div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-gray-400 font-bold mb-1">Environment</label>
                <select v-model="form.tier" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
                  <option :value="1">Production</option>
                  <option :value="2">Non-Production</option>
                </select>
              </div>
              <div>
                <label class="block text-gray-400 font-bold mb-1">Platform Type</label>
                <select v-model="form.platform_override" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
                  <option value="auto">Auto Detect (Agent Report)</option>
                  <option value="baremetal">Physical / Baremetal</option>
                  <option value="vm">Virtual Machine (VM)</option>
                  <option value="lxc">Container (LXC)</option>
                </select>
              </div>
            </div>

            <div class="space-y-2 pt-1">
              <label v-if="form.platform_override !== 'baremetal'" class="flex items-center gap-2 text-gray-300 cursor-pointer">
                <input type="checkbox" v-model="form.is_proxmox_ha" class="accent-cyan-500" />
                <span>Protected by Proxmox HA (Disable remote Power Off)</span>
              </label>
              <label class="flex items-center gap-2 text-gray-300 cursor-pointer">
                <input type="checkbox" v-model="form.is_isolated_net" class="accent-cyan-500" />
                <span>Isolated Network (Local / Air-Gapped without internet)</span>
              </label>
              <label class="flex items-center gap-2 text-gray-300 cursor-pointer">
                <input type="checkbox" v-model="form.allow_web_terminal" class="accent-cyan-500" />
                <span>Allow Web Terminal Access (Interactive Shell)</span>
              </label>
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 px-5 py-3.5 border-t border-gray-800 bg-[#070c18]/80 shrink-0 text-xs">
          <button type="button" @click="closeModal" class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
          <button type="submit" :disabled="saving" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer disabled:opacity-50">
            {{ saving ? 'Registering...' : 'Register & Generate API Key' }}
          </button>
        </div>
      </form>

      <!-- Step 2: Key Reveal -->
      <div v-else class="p-5 space-y-3.5 text-xs">
        <div class="p-2.5 rounded bg-amber-950/50 border border-amber-700/60 text-amber-200">
          Copy this API key now — for security reasons, it is displayed only once and cannot be retrieved later.
        </div>

        <div>
          <label class="block text-gray-400 font-bold mb-1">Agent API Key ({{ revealedHostname }})</label>
          <div class="flex gap-2">
            <input :value="revealedKey" readonly class="flex-1 bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-cyan-300 select-all" />
            <button type="button" @click="copyText(revealedKey)" class="px-3 py-1.5 rounded bg-cyan-950 hover:bg-cyan-800 text-cyan-300 border border-cyan-700 font-bold cursor-pointer">Copy</button>
          </div>
        </div>

        <div>
          <label class="block text-gray-400 font-bold mb-1">Quick Agent Config Setup (Linux)</label>
          <div class="flex gap-2">
            <input :value="setupHint" readonly class="flex-1 bg-[#070c18] border border-gray-800 rounded px-2.5 py-1.5 text-gray-300 select-all" />
            <button type="button" @click="copyText(setupHint)" class="px-3 py-1.5 rounded bg-gray-800 hover:bg-cyan-950 text-cyan-300 border border-gray-700 font-bold cursor-pointer">Copy</button>
          </div>
        </div>

        <div class="flex justify-end pt-3 border-t border-gray-800">
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

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  servers: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'created'])
const toast = useToast()

const defaultForm = () => ({
  hostname: '',
  ip_address: '',
  group_name: '',
  tags: '',
  notes: '',
  tier: 1,
  platform_override: 'auto',
  is_proxmox_ha: false,
  is_isolated_net: false,
  allow_web_terminal: true,
})

const saving = ref(false)
const revealedKey = ref('')
const revealedHostname = ref('')
const form = ref(defaultForm())
const originUrl = computed(() => window.location.origin)
const setupHint = computed(() => `printf 'SERVER_URL="%s"\\nAPI_KEY="%s"\\n' '${originUrl.value}' '${revealedKey.value}' | sudo tee /etc/pantau/agent.conf`)

const existingGroups = computed(() => {
  const set = new Set()
  for (const s of props.servers || []) {
    const g = (s.group_name || '').trim()
    if (g && g.toLowerCase() !== 'default') set.add(g)
  }
  return Array.from(set).sort()
})

async function submit() {
  saving.value = true
  try {
    const payload = { ...form.value }
    if (payload.platform_override === 'baremetal') payload.is_proxmox_ha = false
    const res = await apiFetch('/api/servers', { method: 'POST', body: JSON.stringify(payload) })
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
  form.value = defaultForm()
  emit('close')
}
</script>
