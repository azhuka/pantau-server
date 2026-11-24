<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[35000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
    @click.self="handleClose"
  >
    <div class="relative w-full max-w-md bg-[#0b1325] border border-cyan-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <!-- Modal Header -->
      <div class="flex items-center justify-between px-5 py-3.5 bg-[#0e1930] border-b border-cyan-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span class="font-bold text-gray-200 uppercase tracking-wider text-sm">{{ t('modal_terminal_unlock_title') }}</span>
        </div>
        <button
          @click="handleClose"
          class="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 transition cursor-pointer"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Form Body -->
      <form @submit.prevent="submitUnlock" class="p-5 space-y-4 text-left">
        <div v-if="server" class="p-3 rounded bg-cyan-950/40 border border-cyan-800/50 text-cyan-300 leading-relaxed">
          <div class="font-bold text-gray-200 mb-1">// {{ server.hostname }} ({{ server.ip_address || '127.0.0.1' }})</div>
          <div class="text-[11px] text-gray-400">{{ t('terminal_unlock_desc') }}</div>
        </div>

        <div v-if="errorMsg" class="p-2.5 rounded bg-rose-950/60 border border-rose-500/50 text-rose-300 text-[11px] leading-relaxed flex items-center gap-2">
          <svg class="w-4 h-4 text-rose-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{{ errorMsg }}</span>
        </div>

        <div>
          <label class="block text-gray-300 font-bold mb-1.5">{{ t('terminal_unlock_pwd_label') }}</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
            :placeholder="t('terminal_unlock_pwd_placeholder')"
            ref="pwdInputRef"
          />
        </div>

        <div v-if="userHasTotp">
          <label class="block text-gray-300 font-bold mb-1.5">{{ t('terminal_unlock_totp_label') }}</label>
          <input
            v-model="totp"
            type="text"
            maxlength="6"
            inputmode="numeric"
            pattern="[0-9]*"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 font-mono tracking-widest focus:outline-none focus:border-cyan-400 transition"
            :placeholder="t('terminal_unlock_totp_placeholder')"
          />
        </div>

        <div>
          <label class="block text-gray-300 font-bold mb-1.5">{{ t('terminal_unlock_duration_label') }}</label>
          <select
            v-model="duration"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition cursor-pointer"
          >
            <option value="15">{{ t('terminal_15_min') }}</option>
            <option value="30">{{ t('terminal_30_min') }}</option>
            <option value="60">{{ t('terminal_60_min') }}</option>
          </select>
        </div>

        <div>
          <label class="block text-gray-300 font-bold mb-1.5">{{ t('terminal_unlock_reason_label') }}</label>
          <input
            v-model="reason"
            type="text"
            class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition"
            :placeholder="t('terminal_unlock_reason_placeholder')"
          />
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center justify-end gap-2.5 pt-3 border-t border-cyan-900/60">
          <button
            type="button"
            @click="handleClose"
            class="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold transition cursor-pointer"
          >
            {{ t('btn_cancel') || 'Cancel' }}
          </button>
          <button
            type="submit"
            :disabled="submitting || !password"
            class="px-5 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="submitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            </svg>
            <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
            </svg>
            <span>{{ t('btn_unlock_terminal') }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useI18n } from '../../i18n'

const props = defineProps({
  isOpen: Boolean,
  server: {
    type: Object,
    default: null
  },
  userHasTotp: {
    type: Boolean,
    default: false
  },
  defaultReason: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'unlocked'])
const { t } = useI18n()

const password = ref('')
const totp = ref('')
const duration = ref('15')
const reason = ref('')
const submitting = ref(false)
const errorMsg = ref('')
const pwdInputRef = ref(null)

watch(() => props.isOpen, (newVal) => {
  if (newVal) {
    password.value = ''
    totp.value = ''
    duration.value = '15'
    reason.value = props.defaultReason || ''
    errorMsg.value = ''
    submitting.value = false
    nextTick(() => {
      if (pwdInputRef.value) {
        pwdInputRef.value.focus()
      }
    })
  }
})

function handleClose() {
  emit('close')
}

async function submitUnlock() {
  if (!props.server || !props.server.id) return
  submitting.value = true
  errorMsg.value = ''

  try {
    const token = localStorage.getItem('pantau_token') || ''
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`/api/servers/${props.server.id}/terminal/unlock`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        password: password.value,
        totp: totp.value,
        duration_minutes: parseInt(duration.value, 10),
        reason: reason.value
      })
    })

    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(data.detail || `HTTP ${res.status}`)
    }

    if (data && data.ok) {
      emit('unlocked', {
        server: props.server,
        remaining_seconds: data.remaining_seconds
      })
      emit('close')
    } else {
      errorMsg.value = translateError(data?.message || data?.detail)
    }
  } catch (err) {
    errorMsg.value = translateError(err.message)
  } finally {
    submitting.value = false
  }
}

function translateError(msg) {
  if (!msg) return t('terminal_auth_error')
  const str = String(msg)
  if (str.includes('Invalid account password') || str.includes('Password akun salah') || str.includes('Invalid password')) {
    return t('terminal_err_invalid_pwd')
  }
  if (str.includes('2FA') || str.includes('TOTP')) {
    return t('terminal_err_invalid_totp')
  }
  if (str.includes('password is required') || str.includes('password diperlukan')) {
    return t('terminal_err_pwd_required')
  }
  return str
}
</script>
