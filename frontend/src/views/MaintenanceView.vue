<template>
  <div class="space-y-4">
    <div class="flex flex-col sm:flex-row items-center justify-between gap-3 bg-noc-card border border-noc-border p-3 rounded-lg">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Jadwal Jendela Pemeliharaan (Maintenance Windows)</span>
          <span class="noc-badge noc-badge-purple">{{ windows.length }} jadwal</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Meredam alarm dan notifikasi kegagalan layanan selama masa pemeliharaan terencana</p>
      </div>

      <button @click="showAddModal = true" class="noc-btn noc-btn-primary py-1.5 px-3">
        + Buat Jadwal Pemeliharaan
      </button>
    </div>

    <!-- Windows Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-24">Status</th>
            <th>Judul Pemeliharaan</th>
            <th>Cakupan Node</th>
            <th>Waktu Mulai</th>
            <th>Waktu Selesai</th>
            <th>Dibuat Oleh</th>
            <th class="w-32 text-right">Tindakan</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="w in windows" :key="w.id">
            <td>
              <span
                class="noc-badge uppercase font-bold"
                :class="{
                  'noc-badge-purple': w.status === 'active',
                  'noc-badge-cyan': w.status === 'scheduled',
                  'noc-badge-green': w.status === 'completed',
                  'noc-badge-gray': w.status === 'cancelled',
                }"
              >
                {{ w.status }}
              </span>
            </td>
            <td class="font-bold text-xs text-noc-text">
              <div>{{ w.title }}</div>
              <div v-if="w.description" class="text-[11px] text-noc-dim font-normal mt-0.5">{{ w.description }}</div>
            </td>
            <td class="text-xs text-noc-muted">
              <span v-if="w.scope_type === 'all'" class="font-mono text-noc-cyan">Semua Server</span>
              <span v-else class="font-mono text-noc-text">{{ w.scope_target || 'Node Terpilih' }}</span>
            </td>
            <td class="font-mono text-xs text-noc-muted">{{ w.start_time_str || w.start_time }}</td>
            <td class="font-mono text-xs text-noc-muted">{{ w.end_time_str || w.end_time }}</td>
            <td class="text-xs text-noc-dim">{{ w.created_by }}</td>
            <td class="text-right space-x-1">
              <button
                v-if="w.status === 'active' || w.status === 'scheduled'"
                @click="completeWindow(w)"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-emerald-400"
              >
                Selesai
              </button>
              <button
                v-if="w.status === 'active' || w.status === 'scheduled'"
                @click="cancelWindow(w)"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-rose-400"
              >
                Batalkan
              </button>
            </td>
          </tr>
          <tr v-if="windows.length === 0">
            <td colspan="7" class="text-center py-8 text-noc-muted">Tidak ada jadwal jendela pemeliharaan saat ini</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const windows = ref([])
const showAddModal = ref(false)

async function fetchWindows() {
  try {
    const data = await api.get('/api/maintenance-windows')
    windows.value = data?.windows || []
  } catch (err) {
    console.error('Gagal mengambil jadwal pemeliharaan:', err)
  }
}

async function completeWindow(w) {
  if (!confirm(`Selesaikan jadwal pemeliharaan "${w.title}" sekarang?`)) return
  try {
    await api.post(`/api/maintenance-windows/${w.id}/complete`)
    await fetchWindows()
  } catch (err) {
    alert('Gagal menyelesaikan jadwal: ' + err.message)
  }
}

async function cancelWindow(w) {
  if (!confirm(`Batalkan jadwal pemeliharaan "${w.title}"?`)) return
  try {
    await api.post(`/api/maintenance-windows/${w.id}/cancel`)
    await fetchWindows()
  } catch (err) {
    alert('Gagal membatalkan jadwal: ' + err.message)
  }
}

onMounted(() => {
  fetchWindows()
})
</script>
