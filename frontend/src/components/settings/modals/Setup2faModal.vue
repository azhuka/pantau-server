<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-mono">
    <div class="w-full max-w-lg bg-[#080d1a] border border-cyan-500/40 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
      <!-- Header -->
      <div class="p-4 bg-[#0a1122] border-b border-cyan-900/40 flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="w-3 h-3 rounded-full bg-cyan-400"></div>
          <div>
            <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider">
              Setup Autentikasi Dua Langkah (2FA)
            </h3>
            <p class="text-[11px] text-gray-400 font-mono mt-0.5">
              Standar RFC 6238 TOTP (Google Authenticator / Aegis / Authy)
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

      <!-- Body -->
      <div class="p-4 space-y-4 overflow-y-auto text-xs">
        <!-- Step 1: Scan QR / Secret (Before Confirmation) -->
        <div v-if="!confirmedCodes" class="space-y-4">
          <div v-if="loadingInit" class="text-center py-8 text-gray-400">
            Menyiapkan kunci enkripsi 2FA...
          </div>
          <div v-else class="space-y-4">
            <p class="text-gray-300 text-[11px] leading-relaxed">
              Pindai kode QR di bawah ini menggunakan aplikasi autentikator di ponsel Anda (Google Authenticator, Aegis, 2FAS, atau Authy):
            </p>

            <div class="flex flex-col sm:flex-row items-center gap-4 p-3 rounded-lg bg-[#0e1628] border border-gray-800">
              <div v-if="initData?.qr_data_url" class="p-2 bg-white rounded-lg flex-shrink-0">
                <img :src="initData.qr_data_url" alt="QR Code 2FA" class="w-32 h-32" />
              </div>
              <div class="space-y-2 flex-1">
                <span class="text-[10px] text-gray-400 block uppercase font-semibold">Kunci Rahasia Manual:</span>
                <div class="p-2 rounded bg-black/60 border border-gray-800 font-mono text-[11px] text-cyan-300 font-bold select-all break-all">
                  {{ initData?.formatted_secret || initData?.raw_secret }}
                </div>
                <button
                  type="button"
                  @click="copySecret"
                  class="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer font-bold"
                >
                  <span>{{ copied ? '✔ Tersalin ke Clipboard' : 'Salin Kunci Manual' }}</span>
                </button>
              </div>
            </div>

            <!-- Form Verifikasi 6 Digit -->
            <form @submit.prevent="handleConfirm" class="space-y-3 pt-2 border-t border-gray-800">
              <div>
                <label class="block text-[11px] font-semibold text-gray-200 uppercase mb-1">
                  Masukkan Kode 6-Digit dari Aplikasi Autentikator:
                </label>
                <input
                  v-model="verificationCode"
                  type="text"
                  required
                  maxlength="6"
                  pattern="[0-9]{6}"
                  placeholder="000000"
                  autocomplete="off"
                  class="w-full bg-[#111827] border border-gray-800 focus:border-cyan-500 rounded px-3 py-2 text-center text-lg font-mono tracking-widest text-white focus:outline-none"
                />
              </div>

              <div v-if="errorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[11px]">
                {{ errorMsg }}
              </div>

              <button
                type="submit"
                :disabled="confirming || verificationCode.length !== 6"
                class="w-full py-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-bold transition cursor-pointer"
              >
                {{ confirming ? 'Memverifikasi...' : 'Verifikasi & Aktifkan 2FA' }}
              </button>
            </form>
          </div>
        </div>

        <!-- Step 2: Show Recovery Codes (After Confirmation) -->
        <div v-else class="space-y-3">
          <div class="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200">
            <h4 class="font-bold text-sm flex items-center gap-1.5 mb-1 text-amber-300">
              <span>✔</span>
              <span>2FA Enabled Successfully! Backup Recovery Codes:</span>
            </h4>
            <p class="text-[11px] leading-relaxed">
              Save these recovery codes in a secure location. Each code can only be used once.
            </p>
          </div>

          <div class="grid grid-cols-2 gap-2 p-3 rounded-lg bg-[#0e1628] border border-gray-800">
            <div
              v-for="(code, idx) in confirmedCodes"
              :key="idx"
              class="p-2 rounded bg-black/60 border border-gray-800 text-center font-mono font-bold text-cyan-300 text-sm tracking-wider select-all"
            >
              {{ code }}
            </div>
          </div>

          <div class="flex items-center gap-2 pt-2">
            <button
              @click="copyAllCodes"
              class="flex-1 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold transition cursor-pointer text-center"
            >
              {{ copiedCodes ? '✔ Semua Kode Tersalin' : 'Salin Semua Kode' }}
            </button>
            <button
              @click="downloadCodes"
              class="flex-1 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold transition cursor-pointer text-center"
            >
              Unduh File (.txt)
            </button>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="p-3 bg-[#0a1122] border-t border-cyan-900/40 flex items-center justify-end">
        <button
          @click="finishSetup"
          class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer"
        >
          {{ confirmedCodes ? 'Done' : 'Cancel' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const emit = defineEmits(['close', 'enabled'])

const loadingInit = ref(true)
const initData = ref(null)
const verificationCode = ref('')
const confirming = ref(false)
const errorMsg = ref('')
const confirmedCodes = ref(null)
const copied = ref(false)
const copiedCodes = ref(false)

onMounted(async () => {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/2fa/init', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Gagal inisialisasi 2FA')
    initData.value = data
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loadingInit.value = false
  }
})

function copySecret() {
  const secret = initData.value?.raw_secret || ''
  navigator.clipboard.writeText(secret)
  copied.value = true
  setTimeout(() => { copied.value = false }, 3000)
}

async function handleConfirm() {
  if (!initData.value?.raw_secret) return
  confirming.value = true
  errorMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/2fa/confirm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        secret: initData.value.raw_secret,
        code: verificationCode.value.trim(),
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Kode autentikasi tidak valid')
    confirmedCodes.value = data.recovery_codes || []
    emit('enabled')
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    confirming.value = false
  }
}

function copyAllCodes() {
  if (!confirmedCodes.value) return
  const text = confirmedCodes.value.join('\n')
  navigator.clipboard.writeText(text)
  copiedCodes.value = true
  setTimeout(() => { copiedCodes.value = false }, 3000)
}

function downloadCodes() {
  if (!confirmedCodes.value) return
  const text = `PANTAU SERVER 2FA RECOVERY CODES\nTanggal: ${new Date().toISOString()}\nSimpan kode ini dengan aman:\n\n` + confirmedCodes.value.join('\n')
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pantau_recovery_codes_${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

function finishSetup() {
  emit('close')
}
</script>
