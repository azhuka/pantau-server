<template>
  <div class="max-w-4xl mx-auto space-y-4">
    <!-- Header -->
    <div class="bg-noc-card border border-noc-border p-3.5 rounded-lg flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Profil & Keamanan Akun Operator</span>
          <span class="noc-badge noc-badge-cyan">{{ authStore.user?.username }}</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Pengaturan kata sandi, otentikasi dua faktor (2FA TOTP), dan identitas organisasi</p>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Change Password Card -->
      <div class="noc-card p-4 space-y-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-text flex items-center gap-2 pb-2 border-b border-noc-border">
          <span>🔑</span>
          <span>Ubah Kata Sandi</span>
        </h3>

        <form @submit.prevent="handleChangePassword" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Kata Sandi Saat Ini</label>
            <input
              v-model="oldPassword"
              type="password"
              required
              placeholder="••••••••••••"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Kata Sandi Baru</label>
            <input
              v-model="newPassword"
              type="password"
              required
              placeholder="••••••••••••"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Ulangi Kata Sandi Baru</label>
            <input
              v-model="confirmPassword"
              type="password"
              required
              placeholder="••••••••••••"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <button type="submit" :disabled="savingPassword" class="noc-btn noc-btn-primary w-full py-2">
            {{ savingPassword ? 'Memperbarui...' : 'Simpan Kata Sandi Baru' }}
          </button>
        </form>
      </div>

      <!-- 2FA Security Card -->
      <div class="noc-card p-4 space-y-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-text flex items-center gap-2 pb-2 border-b border-noc-border">
          <span>🛡️</span>
          <span>Otentikasi Dua Faktor (2FA TOTP)</span>
        </h3>

        <div class="text-xs text-noc-muted space-y-2">
          <p>
            Amankan akun Anda dengan aplikasi autentikator standar industri seperti Google Authenticator, Aegis, atau 1Password.
          </p>

          <div class="p-3 rounded bg-noc-bg border border-noc-border flex items-center justify-between">
            <div>
              <div class="font-bold text-noc-text">Status 2FA</div>
              <div class="text-[11px] text-noc-dim">Proteksi lapis kedua pada saat login</div>
            </div>
            <span class="noc-badge noc-badge-green font-bold">AKTIF</span>
          </div>

          <p class="text-[11px] text-noc-dim">
            Kunci pemulihan cadangan dapat digunakan apabila perangkat autentikator hilang atau tidak dapat diakses.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const savingPassword = ref(false)

async function handleChangePassword() {
  if (newPassword.value !== confirmPassword.value) {
    alert('Konfirmasi kata sandi baru tidak cocok!')
    return
  }
  savingPassword.value = true
  try {
    const formData = new FormData()
    formData.append('old_password', oldPassword.value)
    formData.append('new_password', newPassword.value)
    formData.append('confirm_password', confirmPassword.value)
    await api.post('/profile/password', formData)
    alert('Kata sandi berhasil diperbarui!')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (err) {
    alert('Gagal mengubah kata sandi: ' + err.message)
  } finally {
    savingPassword.value = false
  }
}
</script>
