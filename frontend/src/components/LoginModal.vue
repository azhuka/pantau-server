<template>
  <div class="min-h-screen w-full bg-[#06090f] text-gray-100 flex flex-col justify-between p-4 sm:p-6 select-none relative overflow-hidden font-mono">
    <!-- SUBTLE CYBER BACKGROUND AMBIENCE -->
    <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_20%,rgba(14,116,144,0.15)_0%,rgba(6,9,15,1)_70%)] pointer-events-none"></div>
    <div class="absolute inset-0 bg-[linear-gradient(to_right,#080d1a_1px,transparent_1px),linear-gradient(to_bottom,#080d1a_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-30 pointer-events-none"></div>

    <!-- TOP BAR: BRAND MONIKER & LANGUAGE SELECTOR -->
    <header class="relative z-10 flex items-center justify-between w-full max-w-5xl mx-auto pt-2">
      <!-- Cyber Brand Moniker -->
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded bg-cyan-950/70 border border-cyan-400/50 flex items-center justify-center text-cyan-300 shadow-[0_0_12px_rgba(56,189,248,0.35)]">
          <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
            <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
            <line x1="6" y1="6" x2="6.01" y2="6"/>
            <line x1="6" y1="18" x2="6.01" y2="18"/>
          </svg>
        </div>
        <div>
          <div class="font-bold text-sm tracking-wider text-gray-100 flex items-center gap-2">
            <span class="text-cyan-400 font-extrabold">{{ t('app_name') }}</span>
            <span class="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 tracking-normal">
              v0.1.78
            </span>
          </div>
          <div class="text-[10px] text-gray-400 tracking-widest uppercase flex items-center gap-1.5">
            <span class="text-cyan-500/80"></span>
            <span>NOC CONTROL PLANE &amp; ASSET TELEMETRY</span>
          </div>
        </div>
      </div>
    </header>

    <!-- CENTER LOGIN CARD -->
    <div class="relative z-10 w-full max-w-sm mx-auto my-auto py-8">
      <div class="bg-[#0b1220]/95 border border-cyan-500/30 rounded-2xl p-6 sm:p-7 shadow-[0_12px_40px_rgba(0,0,0,0.8)] backdrop-blur-md">
        <!-- Brand Icon & Header -->
        <div class="text-center mb-6">
          <div class="w-12 h-12 rounded-xl bg-cyan-950/80 border border-cyan-400/60 flex items-center justify-center font-black text-cyan-300 text-xl mx-auto shadow-[0_0_15px_rgba(56,189,248,0.25)] mb-3">
            <svg v-if="step === '2fa'" class="w-6 h-6 text-cyan-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <svg v-else class="w-6 h-6 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          </div>
          <h2 class="text-sm font-bold text-gray-100 tracking-wider uppercase">
            {{ step === '2fa' ? t('login_2fa_title') : t('login_title') }}
          </h2>
          <p class="text-xs text-gray-400 mt-1 font-sans">
            {{ step === '2fa' ? t('login_2fa_subtitle') : t('login_subtitle') }}
          </p>
        </div>

        <!-- Step 1: Username & Password -->
        <form v-if="step === 'credentials'" @submit.prevent="handleLogin" class="space-y-4 font-mono">
          <div>
            <label class="block text-xs font-semibold text-gray-300 mb-1.5 uppercase tracking-wider text-[11px]">{{ t('login_username') }}</label>
            <input
              v-model="username"
              type="text"
              required
              autofocus
              autocomplete="username"
              class="w-full bg-[#070c17] border border-cyan-900/50 text-gray-100 text-xs rounded-lg px-3.5 py-2.5 focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_10px_rgba(56,189,248,0.2)] font-mono transition-all"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-gray-300 mb-1.5 uppercase tracking-wider text-[11px]">{{ t('login_password') }}</label>
            <input
              v-model="password"
              type="password"
              required
              autocomplete="current-password"
              class="w-full bg-[#070c17] border border-cyan-900/50 text-gray-100 text-xs rounded-lg px-3.5 py-2.5 focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_10px_rgba(56,189,248,0.2)] font-mono transition-all"
            />
          </div>

          <div v-if="errorMsg" class="p-2.5 rounded bg-rose-950/70 border border-rose-800/80 text-rose-300 text-xs leading-relaxed font-sans">
            {{ errorMsg }}
          </div>

          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 rounded-lg bg-cyan-700 hover:bg-cyan-600 text-white font-bold text-xs transition cursor-pointer disabled:opacity-50 shadow-md uppercase tracking-wider font-mono flex items-center justify-center gap-2 mt-2"
          >
            <svg v-if="loading" class="w-4 h-4 animate-spin text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span>{{ loading ? t('login_verifying') : t('login_button') }}</span>
          </button>
        </form>

        <!-- Step 2: 2FA / TOTP Challenge -->
        <form v-else-if="step === '2fa'" @submit.prevent="handle2faVerify" class="space-y-4 font-mono">
          <div>
            <label class="block text-xs font-semibold text-gray-300 mb-1.5 uppercase tracking-wider text-[11px]">{{ t('login_2fa_label') }}</label>
            <input
              v-model="totpCode"
              type="text"
              required
              maxlength="16"
              autofocus
              autocomplete="one-time-code"
              :placeholder="t('login_2fa_placeholder')"
              class="w-full bg-[#070c17] border border-cyan-500/70 text-cyan-200 text-center text-lg font-mono tracking-widest rounded-lg px-3.5 py-2.5 focus:outline-none focus:border-cyan-300 focus:shadow-[0_0_12px_rgba(56,189,248,0.3)] transition-all"
            />
          </div>

          <div v-if="errorMsg" class="p-2.5 rounded bg-rose-950/70 border border-rose-800/80 text-rose-300 text-xs leading-relaxed font-sans">
            {{ errorMsg }}
          </div>

          <button
            type="submit"
            :disabled="loading || !totpCode.trim()"
            class="w-full py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs transition cursor-pointer disabled:opacity-50 shadow-md uppercase tracking-wider font-mono flex items-center justify-center gap-2"
          >
            <svg v-if="loading" class="w-4 h-4 animate-spin text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
            </svg>
            <span>{{ loading ? t('login_verifying') : t('login_2fa_verify_btn') }}</span>
          </button>

          <button
            type="button"
            @click="resetToCredentials"
            class="w-full text-center text-xs text-gray-400 hover:text-cyan-300 cursor-pointer pt-1 transition"
          >
            {{ t('login_2fa_back') }}
          </button>
        </form>
      </div>
    </div>

    <!-- BOTTOM SYSTEM FOOTER -->
    <footer class="relative z-10 w-full max-w-5xl mx-auto pb-2 flex flex-col sm:flex-row items-center justify-between text-[11px] text-gray-400 font-mono gap-2 border-t border-gray-800/60 pt-3">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
        <span class="text-gray-300 font-semibold tracking-wider">PANTAU SERVER CONTROL PLANE</span>
      </div>
      <div class="text-gray-400">
        <span>KERNEL-GRADE PHYSICAL TELEMETRY</span>
        <span class="mx-2">·</span>
        <span>256-BIT ENCRYPTED SESSION</span>
      </div>
    </footer>
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
    let data = {}
    try {
      data = await res.json()
    } catch (parseErr) {
      data = { detail: res.statusText || 'Server error (' + res.status + ')' }
    }

    if (res.ok) {
      if (data.requires_2fa) {
        preauthToken.value = data.preauth_token; step.value = '2fa'; totpCode.value = ''; errorMsg.value = ''
      } else if (data.access_token) {
        localStorage.setItem('pantau_token', data.access_token); emit('logged-in', data.user)
      } else {
        errorMsg.value = data.detail || t('login_invalid')
      }
    } else {
      errorMsg.value = data.detail || t('login_invalid')
    }
  } catch (err) {
    errorMsg.value = t('login_conn_fail') + (err.message || err)
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
    let data = {}
    try {
      data = await res.json()
    } catch (parseErr) {
      data = { detail: res.statusText || 'Server error (' + res.status + ')' }
    }

    if (res.ok && data.access_token) {
      localStorage.setItem('pantau_token', data.access_token)
      emit('logged-in', data.user)
    } else {
      errorMsg.value = data.detail || 'Invalid 2FA code'
    }
  } catch (err) {
    errorMsg.value = t('login_conn_fail') + (err.message || err)
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
