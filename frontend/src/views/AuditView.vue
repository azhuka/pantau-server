<template>
  <div class="space-y-4">
    <div class="bg-noc-card border border-noc-border p-3 rounded-lg flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Catatan Audit & Jejak Operasional</span>
          <span class="noc-badge noc-badge-cyan">{{ logs.length }} entri</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Rekam jejak seluruh aksi operator, perubahan konfigurasi, dan eksekusi kendali jarak jauh</p>
      </div>

      <button @click="fetchLogs" class="noc-btn noc-btn-secondary py-1 px-3">
        Segarkan
      </button>
    </div>

    <!-- Audit Logs Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-36">Waktu Kejadian</th>
            <th class="w-28">Operator</th>
            <th class="w-36">Tindakan (Action)</th>
            <th>Target Sistem</th>
            <th>Hasil Eksekusi</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td class="font-mono text-xs text-noc-muted">{{ log.created_at_str || log.created_at }}</td>
            <td class="font-bold text-xs text-noc-cyan">{{ log.username }}</td>
            <td class="font-mono text-xs text-noc-text font-semibold uppercase">{{ log.action }}</td>
            <td class="font-mono text-xs text-noc-dim">{{ log.target || '—' }}</td>
            <td>
              <span
                class="noc-badge"
                :class="log.result?.includes('gagal') ? 'noc-badge-red' : 'noc-badge-green'"
              >
                {{ log.result || 'berhasil' }}
              </span>
            </td>
          </tr>
          <tr v-if="logs.length === 0">
            <td colspan="5" class="text-center py-8 text-noc-muted">Belum ada riwayat audit log tercatat</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const logs = ref([])

async function fetchLogs() {
  try {
    const data = await api.get('/api/logs/dashboard')
    logs.value = data?.logs || []
  } catch (err) {
    console.error('Gagal mengambil audit logs:', err)
  }
}

onMounted(() => {
  fetchLogs()
})
</script>
