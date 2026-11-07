<template>
  <div class="min-h-screen flex items-center justify-center p-4 bg-noc-bg bg-radial-gradient">
    <div class="w-full max-w-sm noc-card p-6 border-noc-border/80 shadow-2xl relative">
      <div class="text-center mb-6">
        <div class="w-10 h-10 mx-auto rounded-lg bg-noc-cyan/10 border border-noc-cyan/30 flex items-center justify-center text-noc-cyan font-mono text-sm font-bold shadow-inner mb-3">
          PS
        </div>
        <h1 class="text-base font-bold text-noc-text tracking-tight uppercase">
          PANTAU <span class="text-noc-cyan">SERVER</span>
        </h1>
        <p class="text-xs text-noc-muted mt-1">Sistem Pemantauan NOC & Orkestrasi Server</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div v-if="error" class="p-2.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-start gap-2">
          <span>⚠️</span>
          <span>{{ error }}</span>
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Pengguna</label>
          <input
            v-model="username"
            type="text"
            required
            autocomplete="username"
            placeholder="admin / operator"
            class="w-full px-3 py-2 bg-noc-bg border border-noc-border rounded text-xs text-noc-text placeholder-noc-muted focus:outline-none focus:border-noc-cyan transition-colors"
          />
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Kata Sandi</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            placeholder="••••••••••••"
            class="w-full px-3 py-2 bg-noc-bg border border-noc-border rounded text-xs text-noc-text placeholder-noc-muted focus:outline-none focus:border-noc-cyan transition-colors"
          />
        </div>

        <div v-if="requires2FA">
          <label class="block text-[11px] font-semibold text-noc-cyan uppercase mb-1">Kode Otentikasi 2FA / Pemulihan</label>
          <input
            v-model="totpCode"
            type="text"
            required
            autocomplete="one-time-code"
            placeholder="6 digit kode TOTP"
            class="w-full px-3 py-2 bg-noc-bg border border-noc-cyan/50 rounded text-xs text-noc-text placeholder-noc-muted font-mono tracking-widest focus:outline-none focus:border-noc-cyan transition-colors"
          />
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full noc-btn noc-btn-primary py-2 text-xs font-semibold shadow-md mt-2 flex items-center justify-center gap-2"
        >
          <span v-if="loading" class="w-3.5 h-3.5 border-2 border-slate-900 border-t-transparent rounded-full animate-spin"></span>
          <span>{{ loading ? 'Memverifikasi...' : (requires2FA ? 'Verifikasi 2FA' : 'Masuk ke Dasbor') }}</span>
        </button>
      </form>

      <div class="mt-6 pt-4 border-t border-noc-border/50 text-center text-[10px] text-noc-muted">
        Otentikasi Aman · Enkripsi Sesi Kriptografis
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const totpCode = ref('')
const requires2FA = ref(false)
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    if (!requires2FA.value) {
      // Step 1: Normal Login Form Submission
      const formData = new FormData()
      formData.append('username', username.value)
      formData.append('password', password.value)

      const res = await fetch('/login', {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: formData,
        credentials: 'same-origin',
      })

      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        if (data.requires_2fa) {
          requires2FA.value = true
          return
        }
        await authStore.fetchCurrentUser()
        router.push('/dashboard')
      } else {
        error.value = data?.detail || 'Kredensial tidak valid. Silakan periksa nama pengguna dan kata sandi.'
      }
    } else {
      // Step 2: 2FA Submission
      const formData = new FormData()
      formData.append('code', totpCode.value)

      const res = await fetch('/login/2fa', {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: formData,
        credentials: 'same-origin',
      })

      const data = await res.json().catch(() => ({}))
      if (res.ok) {
        await authStore.fetchCurrentUser()
        router.push('/dashboard')
      } else {
        error.value = data?.detail || 'Kode 2FA tidak valid atau sudah kedaluwarsa.'
      }
    }
  } catch (err) {
    error.value = err.message || 'Terjadi kendala jaringan saat menghubungi server.'
  } finally {
    loading.value = false
  }
}
</script>
