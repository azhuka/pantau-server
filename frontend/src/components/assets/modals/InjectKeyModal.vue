<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
    @click.self="$emit('close')"
  >
    <div class="relative w-full max-w-md bg-[#0b1325] border border-cyan-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <!-- Modal Header -->
      <div class="flex items-center justify-between px-5 py-3.5 bg-[#0e1930] border-b border-cyan-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="7.5" cy="15.5" r="5.5"/>
            <path d="m21 2-9.6 9.6"/>
            <path d="m15.5 7.5 3 3L22 7l-3-3"/>
          </svg>
          <span class="font-bold text-gray-200 uppercase tracking-wider text-sm">{{ t('modal_inject_key_title') }}</span>
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
      <form @submit.prevent="submitKey" class="p-5 space-y-4 text-left">
        <div v-if="server" class="p-3 rounded bg-cyan-950/40 border border-cyan-800/50 text-cyan-300 leading-relaxed">
          <div class="font-bold text-gray-200 mb-1">// {{ server.hostname }} ({{ server.ip_address }})</div>
          <div class="text-[11px] text-gray-400">{{ t('inject_key_desc') }}</div>
        </div>

        <div>
          <label class="block text-gray-400 font-bold mb-1.5">{{ t('inject_key_password') }}</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
            placeholder="••••••••••••"
          />
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
            :disabled="submitting || !password"
            class="px-5 py-2 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="submitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            </svg>
            <span>{{ t('act_inject_key') }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  isOpen: Boolean,
  server: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'success'])
const { t } = useI18n()
const toast = useToast()

const submitting = ref(false)
const password = ref('')

watch(() => props.isOpen, (open) => {
  if (open) {
    password.value = ''
  }
})

async function submitKey() {
  if (!props.server || !password.value) return
  submitting.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/inject-key`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ password: password.value })
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      emit('success', data.message || 'Key injected')
      emit('close')
    } else {
      toast.error(data.detail || data.error || 'Failed to inject SSH key')
    }
  } catch (err) {
    toast.error('Error: ' + err.message)
  } finally {
    submitting.value = false
  }
}
</script>
