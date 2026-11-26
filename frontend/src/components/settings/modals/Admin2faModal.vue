<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-mono">
    <div class="w-full max-w-md bg-[#080d1a] border border-amber-500/40 rounded-xl shadow-2xl overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="p-4 bg-[#0a1122] border-b border-amber-900/40 flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="w-3 h-3 rounded-full bg-amber-400"></div>
          <div>
            <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider">
              Manage Operator 2FA
            </h3>
            <p class="text-[11px] text-gray-400 font-mono mt-0.5">
              Emergency Two-Factor Authentication Reset
            </p>
          </div>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-white text-lg p-1 transition cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Content -->
      <div class="p-4 space-y-4 text-xs">
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-gray-400">Username:</span>
            <span class="font-bold text-gray-100 font-mono">{{ user.username }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-gray-400">Role:</span>
            <span class="text-cyan-300 font-semibold">{{ user.role }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-gray-400">Current 2FA Status:</span>
            <span
              class="font-bold"
              :class="user.totp_enabled ? 'text-emerald-400' : 'text-amber-400'"
            >
              {{ user.totp_enabled ? '● 2FA Active' : '○ 2FA Disabled' }}
            </span>
          </div>
        </div>

        <div v-if="user.totp_enabled" class="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200 text-[11px] leading-relaxed">
          <p class="font-bold mb-1">Master Admin Notice:</p>
          Resetting 2FA will immediately revoke the current TOTP secret key and all backup recovery codes for operator <strong>{{ user.username }}</strong>.
        </div>
        <div v-else class="p-3 rounded-lg bg-gray-900/60 border border-gray-800 text-gray-400 text-[11px]">
          This operator has not enabled 2FA yet. The operator can configure it independently upon signing in.
        </div>

        <div v-if="errorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[11px]">
          {{ errorMsg }}
        </div>
      </div>

      <!-- Footer -->
      <div class="p-3 bg-[#0a1122] border-t border-amber-900/40 flex items-center justify-end gap-2">
        <button
          @click="$emit('close')"
          class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-mono transition cursor-pointer"
        >
          Cancel
        </button>
        <button
          v-if="user.totp_enabled"
          @click="handleReset2fa"
          :disabled="loading"
          class="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer flex items-center gap-1.5"
        >
          <span>{{ loading ? 'Processing...' : 'Reset 2FA' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { confirmAction } from '../../../utils/useToast'

const props = defineProps({
  user: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close', 'updated'])

const loading = ref(false)
const errorMsg = ref('')

async function handleReset2fa() {
  const ok = await confirmAction({
    title: 'Reset Operator 2FA',
    message: `Are you sure you want to reset and disable 2FA for operator ${props.user.username}?`,
    confirmText: 'Reset 2FA',
    variant: 'danger',
  })
  if (!ok) return
  loading.value = true
  errorMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${props.user.id}/reset-2fa`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to reset operator 2FA')
    emit('updated')
    emit('close')
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loading.value = false
  }
}
</script>