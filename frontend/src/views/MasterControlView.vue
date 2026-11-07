<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="bg-noc-card border border-noc-border p-3.5 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-3">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Pusat Kendali Master (Master Control Center)</span>
          <span class="noc-badge noc-badge-amber">Master Administrator</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Pemantauan infrastruktur server dashboard, kapasitas basis data MySQL, dan pemeliharaan internal</p>
      </div>

      <div class="flex items-center gap-2">
        <button
          @click="optimizeDatabase"
          :disabled="optimizing"
          class="noc-btn noc-btn-primary py-1.5 px-3 flex items-center gap-1.5 shadow-md"
        >
          <span v-if="optimizing" class="w-3.5 h-3.5 border-2 border-slate-900 border-t-transparent rounded-full animate-spin"></span>
          <span>{{ optimizing ? 'Mengoptimasi...' : '⚡ Optimasi Basis Data' }}</span>
        </button>
      </div>
    </div>

    <!-- Optimization Feedback Notice -->
    <div v-if="optimizeResult" class="p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center justify-between">
      <span>{{ optimizeResult }}</span>
      <button @click="optimizeResult = ''" class="text-emerald-400 hover:text-white">✕</button>
    </div>

    <!-- Telemetry Host Dashboard Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="noc-card p-3">
        <div class="text-[11px] font-semibold text-noc-dim uppercase">CPU Host Dashboard</div>
        <div class="text-2xl font-bold font-mono text-noc-text mt-1">{{ Math.round(status?.cpu || 0) }}%</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Prosesor server utama</div>
      </div>

      <div class="noc-card p-3">
        <div class="text-[11px] font-semibold text-noc-dim uppercase">RAM Host Dashboard</div>
        <div class="text-2xl font-bold font-mono text-emerald-400 mt-1">{{ Math.round(status?.ram_pct || 0) }}%</div>
        <div class="text-[10px] text-noc-muted mt-0.5">{{ status?.ram_str || 'Memori terpakai' }}</div>
      </div>

      <div class="noc-card p-3">
        <div class="text-[11px] font-semibold text-noc-dim uppercase">Disk Host Dashboard</div>
        <div class="text-2xl font-bold font-mono text-noc-cyan mt-1">{{ Math.round(status?.disk_pct || 0) }}%</div>
        <div class="text-[10px] text-noc-muted mt-0.5">{{ status?.disk_str || 'Partisi root' }}</div>
      </div>

      <div class="noc-card p-3">
        <div class="text-[11px] font-semibold text-noc-dim uppercase">Waktu Operasional</div>
        <div class="text-2xl font-bold font-mono text-noc-text mt-1">{{ status?.uptime_str || '—' }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Uptime daemon FastAPI</div>
      </div>
    </div>

    <!-- Database Table Storage Allocation -->
    <div class="noc-card p-3.5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim flex items-center gap-2">
          <span>🗄️</span>
          <span>Alokasi Penyimpanan Tabel Basis Data (MariaDB / MySQL)</span>
        </h3>
        <span class="font-mono text-xs font-semibold text-noc-cyan">
          Total Ukuran Data: {{ dbStatus?.total_size_mb || 0 }} MB
        </span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Nama Tabel</th>
              <th>Ukuran Penyimpanan (MB)</th>
              <th>Estimasi Jumlah Baris (Rows)</th>
              <th>Proporsi Penyimpanan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in dbStatus?.tables || []" :key="t.table">
              <td class="font-mono font-bold text-xs text-noc-cyan">{{ t.table }}</td>
              <td class="font-mono text-xs text-noc-text">{{ t.size_mb }} MB</td>
              <td class="font-mono text-xs text-noc-dim">{{ t.rows?.toLocaleString() }} baris</td>
              <td class="w-64">
                <div class="flex items-center gap-2">
                  <div class="flex-1 h-1.5 bg-noc-surface rounded-full overflow-hidden">
                    <div
                      class="h-full bg-noc-cyan rounded-full"
                      :style="{ width: `${Math.min(((t.size_mb || 0) / (dbStatus?.total_size_mb || 1)) * 100, 100)}%` }"
                    ></div>
                  </div>
                  <span class="font-mono text-[10px] text-noc-muted w-10 text-right">
                    {{ Math.round(((t.size_mb || 0) / (dbStatus?.total_size_mb || 1)) * 100) }}%
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Data Retention Policies -->
    <div class="noc-card p-3.5">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>🧹</span>
        <span>Kebijakan Retensi Data Otomatis (Automatic Retention Cleanup)</span>
      </h3>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mt-3">
        <div class="p-3 rounded bg-noc-bg border border-noc-border">
          <div class="font-bold text-noc-text">Metrik Layanan Mentah</div>
          <div class="font-mono text-noc-cyan font-bold text-base mt-1">7 Hari</div>
          <div class="text-[11px] text-noc-muted mt-1">Data metrik polling dipangkas otomatis setiap 24 jam</div>
        </div>

        <div class="p-3 rounded bg-noc-bg border border-noc-border">
          <div class="font-bold text-noc-text">Snapshot Kinerja Jam-jaman</div>
          <div class="font-mono text-emerald-400 font-bold text-base mt-1">90 Hari</div>
          <div class="text-[11px] text-noc-muted mt-1">Agregasi rollup performa CPU, RAM, dan Disk disimpan 3 bulan</div>
        </div>

        <div class="p-3 rounded bg-noc-bg border border-noc-border">
          <div class="font-bold text-noc-text">Antrean Log & Perintah Selesai</div>
          <div class="font-mono text-purple-400 font-bold text-base mt-1">100 Entri / Node</div>
          <div class="text-[11px] text-noc-muted mt-1">Menjaga tabel log_requests tetap ramping dan bebas degradasi</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const status = ref(null)
const dbStatus = ref(null)
const optimizing = ref(false)
const optimizeResult = ref('')

async function fetchData() {
  try {
    const data = await api.get('/api/master-control/status')
    if (data) {
      status.value = data.system
      dbStatus.value = data.database
    }
  } catch (err) {
    console.error('Gagal mengambil status Master Control:', err)
  }
}

async function optimizeDatabase() {
  if (!confirm('Peringatan: Jalankan prosedur OPTIMIZE TABLE pada seluruh tabel database?')) return
  optimizing.value = true
  optimizeResult.value = ''
  try {
    const res = await api.post('/api/master-control/optimize-db')
    optimizeResult.value = res.detail || 'Optimasi tabel database berhasil dijalankan!'
    await fetchData()
  } catch (err) {
    alert('Optimasi gagal: ' + err.message)
  } finally {
    optimizing.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>
