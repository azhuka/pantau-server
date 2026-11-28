<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="relative w-full max-w-lg bg-[#0b1325] border border-cyan-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <!-- Modal Header -->
      <div class="flex items-center justify-between px-5 py-3.5 bg-[#0e1930] border-b border-cyan-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            <path d="m15 5 4 4"/>
          </svg>
          <span class="font-bold text-gray-200 uppercase tracking-wider text-sm">{{ t('modal_edit_host_title') }}</span>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 transition cursor-pointer"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Form Body -->
      <form @submit.prevent="saveHost" class="p-5 space-y-4 text-left">
        <!-- Hostname -->
        <div>
          <label class="block text-gray-400 font-bold mb-1.5">{{ t('host_field_name') }}</label>
          <input
            v-model="form.hostname"
            type="text"
            required
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
          />
        </div>

        <!-- IP Address -->
        <div>
          <label class="block text-gray-400 font-bold mb-1.5">{{ t('host_field_ip') }}</label>
          <input
            v-model="form.ip_address"
            type="text"
            required
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
          />
        </div>

        <!-- Group Name & Environment -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-gray-400 font-bold mb-1.5">{{ t('host_field_group') }}</label>
            <input
              v-model="form.group_name"
              type="text"
              class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
            />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1.5">{{ t('host_field_tier') }}</label>
            <select
              v-model="form.tier"
              class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition cursor-pointer"
            >
              <option :value="1">Production — Crucial (Core)</option>
              <option :value="3">Production — Standard (Supporting)</option>
              <option :value="2">Non-Production (Staging / Test)</option>
            </select>
          </div>
        </div>

        <!-- Platform Override -->
        <div>
          <label class="block text-gray-400 font-bold mb-1.5">{{ t('host_field_platform') }}</label>
          <select
            v-model="form.platform_override"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition cursor-pointer"
          >
            <option value="auto">{{ t('platform_auto') }}</option>
            <option value="baremetal">{{ t('platform_baremetal') }}</option>
            <option value="vm">{{ t('platform_vm') }}</option>
            <option value="lxc">{{ t('platform_lxc') }}</option>
          </select>
        </div>

        <!-- Master Admin: Regenerate Agent API Key -->
        <div v-if="currentUser?.is_master_admin" class="pt-3 border-t border-cyan-900/40 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold text-amber-300 uppercase">Agent API Key</span>
            <button
              type="button"
              @click="regenerateKey"
              :disabled="regenerating"
              class="px-3 py-1 rounded bg-amber-950/70 hover:bg-amber-900 text-amber-300 border border-amber-700/60 text-[11px] font-bold transition cursor-pointer disabled:opacity-40"
            >
              {{ regenerating ? 'Rotating...' : 'Regenerate API Key' }}
            </button>
          </div>
          <div v-if="newApiKey" class="p-2.5 rounded bg-emerald-950/50 border border-emerald-700/60 flex items-center justify-between gap-2">
            <code class="text-[11px] text-emerald-300 break-all select-all">{{ newApiKey }}</code>
            <button
              type="button"
              @click="copyNewKey"
              class="px-2 py-1 rounded bg-emerald-800 hover:bg-emerald-700 text-white text-[10px] font-bold shrink-0 cursor-pointer"
            >
              Copy
            </button>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center justify-end gap-2.5 pt-3 border-t border-cyan-900/60">
          <button
            type="button"
            @click="$emit('close')"
            class="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold transition cursor-pointer"
          >
            {{ t('btn_cancel') || 'Cancel' }}
          </button>
          <button
            type="submit"
            :disabled="submitting"
            class="px-5 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="submitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            </svg>
            <span>{{ t('btn_save') || 'Save' }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useModalEsc } from '../../../utils/useModalEsc'
import { ref, watch } from 'vue'
import { useI18n } from '../../../i18n'
import { confirmAction, useToast } from '../../../utils/useToast'

const toast = useToast()

const props = defineProps({
  isOpen: Boolean,
  server: {
    type: Object,
    default: null
  },
  currentUser: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'updated'])
const { t } = useI18n()

const submitting = ref(false)
const regenerating = ref(false)
const newApiKey = ref('')
const form = ref({
  hostname: '',
  ip_address: '',
  group_name: '',
  tier: 1,
  platform_override: 'auto'
})

watch(() => props.server, (s) => {
  newApiKey.value = ''
  if (s) {
    form.value = {
      hostname: s.hostname || '',
      ip_address: s.ip_address || '',
      group_name: s.group_name || '',
      tier: s.tier || 1,
      platform_override: s.platform_override || 'auto'
    }
  }
}, { immediate: true })

async function saveHost() {
  if (!props.server) return
  submitting.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify(form.value)
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      emit('updated', data.message || 'Host updated')
      emit('close')
    } else {
      toast.error(data.detail || data.error || 'Failed to update host')
    }
  } catch (err) {
    toast.error('Error: ' + err.message)
  } finally {
    submitting.value = false
  }
}

async function regenerateKey() {
  if (!props.server?.id) return
  const ok = await confirmAction({
    title: 'Regenerate Agent API Key',
    message: `Rotate the API key for ${props.server.hostname}? The current agent key will stop working until updated.`,
    variant: 'danger',
  })
  if (!ok) return
  regenerating.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.server.id}/regenerate-key`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to regenerate API key')
    newApiKey.value = data.api_key
    toast.success('New API key generated. Copy it now — it is shown only once.')
  } catch (err) {
    toast.error(err.message)
  } finally {
    regenerating.value = false
  }
}

function copyNewKey() {
  if (!newApiKey.value) return
  navigator.clipboard.writeText(newApiKey.value).then(() => toast.success('API key copied to clipboard'))
}
useModalEsc(() => props.isOpen, () => emit('close'))
</script>
