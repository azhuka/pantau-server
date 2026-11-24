<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
    <div class="bg-[#111827] border border-[#1f2937] rounded-2xl w-full max-w-sm p-6 shadow-2xl">
      <!-- Brand Icon & Header -->
      <div class="text-center mb-6">
        <div class="w-12 h-12 rounded-xl bg-cyan-700 border border-cyan-500/50 flex items-center justify-center font-black text-white text-xl mx-auto shadow-md mb-3">
          <svg v-if="step === '2fa'" class="w-6 h-6 text-cyan-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <span v-else>P</span>
        </div>
        <h2 class="text-base font-bold text-gray-100 font-mono">
          {{ step === '2fa' ? t('login_2fa_title') : t('login_title') }}
        </h2>
        <p class="text-xs text-gray-400 mt-1 font-mono">
          {{ step === '2fa' ? t('login_2fa_subtitle') : t('login_subtitle') }}
        </p>
      </div>

      <!-- Step 1: Username & Password -->
      <form v-if="step === 'credentials'" @submit.prevent="handleLogin" class="space-y-4 font-mono">
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('login_username') }}</label>
          <input
            v-model="username"
            type="text"
            required
            autocomplete="username"
            placeholder="master-admin / operator"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500 font-mono"
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
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500 font-mono"
          />
        </div>

        <div v-if="errorMsg" class="p-2.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs">
          {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-white font-bold text-xs transition cursor-pointer disabled:opacity-50 shadow-md uppercase tracking-wider"
        >
          {{ loading ? t('login_verifying') : t('login_button') }}
        </button>
      </form>

      <!-- Step 2: 2FA / TOTP Challenge -->
      <form v-else-if="step === '2fa'" @submit.prevent="handle2faVerify" class="space-y-4 font-mono">
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('login_2fa_label') }}</label>
          <input
            v-model="totpCode"
            type="text"
            required
            maxlength="16"
            autofocus
            autocomplete="one-time-code"
            :placeholder="t('login_2fa_placeholder')"
            class="w-full bg-[#161f30] border border-cyan-600/70 text-cyan-200 text-center text-lg font-mono tracking-widest rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-400"
          />
        </div>

        <div v-if="errorMsg" class="p-2.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs">
          {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="loading || !totpCode.trim()"
          class="w-full py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs transition cursor-pointer disabled:opacity-50 shadow-md uppercase tracking-wider"
        >
          {{ loading ? t('login_verifying') : t('login_2fa_verify_btn') }}
        </button>

        <button
          type="button"
          @click="resetToCredentials"
          class="w-full text-center text-xs text-gray-400 hover:text-gray-200 cursor-pointer pt-1 transition"
        >
          {{ t('login_2fa_back') }}
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

const step = ref('credentials') // 'credentials' | '2fa'
const username = ref('')
const password = ref('')
const preauthToken = ref('')
const totpCode = ref('')
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
        username: username.value.trim(),
        password: password.value,
      }),
    })
    const data = await res.json()
    if (res.ok) {
      if (data.requires_2fa) {
        preauthToken.value = data.preauth_token
        step.value = '2fa'
        totpCode.value = ''
        errorMsg.value = ''
      } else if (data.access_token) {
        localStorage.setItem('pantau_token', data.access_token)
        emit('logged-in', data.user)
      } else {
        errorMsg.value = data.detail || t('login_invalid')
      }
    } else {
      errorMsg.value = data.detail || t('login_invalid')
    }
  } catch (err) {
    errorMsg.value = t('login_conn_fail') + err.message
  } finally {
    loading.value = false
  }
}

async function handle2faVerify() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetch('/api/auth/login-2fa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preauth_token: preauthToken.value,
        code: totpCode.value.trim(),
      }),
    })
    const data = await res.json()
    if (res.ok && data.access_token) {
      localStorage.setItem('pantau_token', data.access_token)
      emit('logged-in', data.user)
    } else {
      errorMsg.value = data.detail || 'Invalid 2FA code'
    }
  } catch (err) {
    errorMsg.value = t('login_conn_fail') + err.message
  } finally {
    loading.value = false
  }
}

function resetToCredentials() {
  step.value = 'credentials'
  totpCode.value = ''
  preauthToken.value = ''
  errorMsg.value = ''
}
</script>
