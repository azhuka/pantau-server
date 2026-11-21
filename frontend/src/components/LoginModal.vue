<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
    <div class="bg-[#111827] border border-[#1f2937] rounded-2xl w-full max-w-sm p-6 shadow-2xl">
      <div class="text-center mb-6">
        <div class="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center font-black text-white text-xl mx-auto shadow-md mb-3">
          P
        </div>
        <h2 class="text-base font-bold text-gray-100">{{ t('login_title') }}</h2>
        <p class="text-xs text-gray-400 mt-1">{{ t('login_subtitle') }}</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('login_username') }}</label>
          <input
            v-model="username"
            type="text"
            required
            autocomplete="username"
            placeholder="master-admin / operator"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 font-mono"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('login_password') }}</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            placeholder="••••••••"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 font-mono"
          />
        </div>

        <div v-if="errorMsg" class="p-2 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs">
          {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition cursor-pointer disabled:opacity-50 shadow-md"
        >
          {{ loading ? t('login_verifying') : t('login_button') }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../i18n'

const emit = defineEmits(['logged-in'])
const { t } = useI18n()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
      }),
    })
    const data = await res.json()
    if (res.ok && data.access_token) {
      localStorage.setItem('pantau_token', data.access_token)
      emit('logged-in', data.user)
    } else {
      errorMsg.value = data.detail || t('login_invalid')
    }
  } catch (err) {
    errorMsg.value = t('login_conn_fail') + err.message
  } finally {
    loading.value = false
  }
}
</script>
