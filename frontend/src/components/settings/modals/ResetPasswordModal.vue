<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
    <div class="bg-[#111827] border border-[#1f2937] rounded-xl w-full max-w-sm p-5 shadow-2xl">
      <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-4">
        <h3 class="text-sm font-bold text-gray-100 font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-amber-400"></span>
          <span>{{ t('settings_modal_reset_title') }}: <strong class="text-amber-300 uppercase">{{ user.username }}</strong></span>
        </h3>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-200 text-sm font-mono cursor-pointer"
        >
          &times;
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label class="block text-xs font-mono font-medium text-gray-300 mb-1">
            {{ t('settings_pwd_new') }}
          </label>
          <input
            v-model="newPassword"
            type="password"
            required
            minlength="8"
            placeholder="••••••••"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-amber-500"
          />
          <p class="text-[10px] text-gray-400 font-mono mt-1">{{ t('settings_pwd_requirement') }}</p>
        </div>

        <div v-if="error" class="p-2 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs font-mono">
          {{ error }}
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-gray-800">
          <button
            type="button"
            @click="$emit('close')"
            class="px-3 py-1.5 rounded text-xs font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer"
          >
            {{ t('settings_btn_cancel') }}
          </button>
          <button
            type="submit"
            :disabled="loading"
            class="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer"
          >
            {{ loading ? t('login_verifying') : t('settings_btn_reset') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  user: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'reset'])
const { t } = useI18n()

const newPassword = ref('')
const loading = ref(false)
const error = ref('')

async function handleSubmit() {
  loading.value = true
  error.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${props.user.id}/reset-password`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ new_password: newPassword.value })
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to reset password')
    }
    emit('reset', data)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>
