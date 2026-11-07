<template>
  <div class="space-y-4">
    <!-- Top Action Banner -->
    <div class="flex flex-col sm:flex-row items-center justify-between gap-3 bg-noc-card border border-noc-border p-3 rounded-lg">
      <div>
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-text flex items-center gap-2">
          <span>Pembaruan Paket Sistem Operasi (APT)</span>
          <span
            class="noc-badge"
            :class="upgradableCount > 0 ? 'noc-badge-amber' : 'noc-badge-green'"
          >
            {{ upgradableCount > 0 ? `${upgradableCount} paket menunggu pembaruan` : 'Sistem Mutakhir' }}
          </span>
        </h3>
        <p class="text-[11px] text-noc-muted mt-0.5">Pemindaian keamanan repositori dan eksekusi upgrade paket terisolasi</p>
      </div>

      <div class="flex items-center gap-2">
        <button
          @click="runApt('APT_UPDATE')"
          :disabled="running"
          class="noc-btn noc-btn-secondary py-1 px-3 text-xs"
        >
          Periksa Update (apt update)
        </button>
        <button
          v-if="upgradableCount > 0"
          @click="runApt('APT_UPGRADE_INTERACT')"
          :disabled="running"
          class="noc-btn noc-btn-primary py-1 px-3 text-xs"
        >
          Upgrade Semua Paket
        </button>
      </div>
    </div>

    <!-- Upgradable Packages Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th>Nama Paket</th>
            <th>Versi Tersedia</th>
            <th>Layanan Terdampak</th>
            <th class="w-28 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pkg in packages" :key="pkg.name">
            <td class="font-mono font-bold text-xs text-noc-cyan">{{ pkg.name }}</td>
            <td class="font-mono text-xs text-noc-text">{{ pkg.version || 'Versi baru' }}</td>
            <td class="text-xs text-noc-muted">
              <span v-if="(pkg.services || []).length > 0" class="text-amber-400 font-mono text-[11px]">
                {{ pkg.services.join(', ') }}
              </span>
              <span v-else class="text-noc-muted">—</span>
            </td>
            <td class="text-right">
              <button
                @click="upgradeSinglePackage(pkg.name)"
                :disabled="running"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]"
              >
                Upgrade
              </button>
            </td>
          </tr>
          <tr v-if="packages.length === 0">
            <td colspan="4" class="text-center py-8 text-noc-muted">
              Seluruh paket sistem operasi berada pada versi mutakhir
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Live Execution Modal -->
    <div v-if="activeRequestId" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div class="w-full max-w-3xl h-[70vh] noc-card p-4 border-noc-border shadow-2xl flex flex-col justify-between">
        <div class="flex items-center justify-between pb-2 border-b border-noc-border">
          <div class="font-bold text-xs text-noc-cyan uppercase flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-noc-cyan animate-ping"></span>
            <span>Eksekusi Perintah APT Sedang Berjalan...</span>
          </div>
          <button @click="closeModal" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <div class="flex-1 my-3 bg-[#090d16] border border-noc-border rounded p-3 overflow-y-auto font-mono text-xs text-noc-text whitespace-pre-wrap">
          {{ streamOutput || 'Menghubungi agen klien...' }}
        </div>

        <div class="flex items-center justify-between text-xs text-noc-muted pt-2 border-t border-noc-border">
          <span>Status: {{ executionStatus }}</span>
          <button @click="closeModal" class="noc-btn noc-btn-secondary py-1 px-3">
            Tutup
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
  overview: Object,
})

const emit = defineEmits(['refresh'])
const running = ref(false)
const activeRequestId = ref(null)
const streamOutput = ref('')
const executionStatus = ref('pending')
let pollTimer = null

const upgradableCount = computed(() => {
  return props.overview?.apt_upgradable || 0
})

const packages = computed(() => {
  return props.overview?.apt_packages || []
})

async function runApt(unit, detail = null) {
  running.value = true
  streamOutput.value = ''
  executionStatus.value = 'executing'
  try {
    const res = await api.post('/api/logs/request', {
      server_id: props.serverId,
      unit,
      lines: 300,
      detail,
    })
    activeRequestId.value = res.id
    pollProgress(res.id)
  } catch (err) {
    alert('Gagal memicu perintah: ' + err.message)
    running.value = false
  }
}

async function upgradeSinglePackage(pkgName) {
  if (!confirm(`Upgrade paket ${pkgName}?`)) return
  runApt('PKG_UPGRADE', pkgName)
}

function pollProgress(rid) {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const data = await api.get(`/api/logs/request/${rid}`)
      if (data) {
        executionStatus.value = data.status
        if (data.result) {
          streamOutput.value = data.result
        }
        if (data.status === 'success' || data.status === 'failed') {
          clearInterval(pollTimer)
          pollTimer = null
          running.value = false
          emit('refresh')
        }
      }
    } catch (e) {
      clearInterval(pollTimer)
      pollTimer = null
      running.value = false
    }
  }, 1000)
}

function closeModal() {
  if (pollTimer) clearInterval(pollTimer)
  activeRequestId.value = null
  running.value = false
}
</script>
