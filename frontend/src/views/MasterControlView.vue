<template>
  <div>
    <div class="topbar">
      <h2>Pusat Kendali Sistem (Master Control)</h2>
      <div style="display:flex;gap:6px">
        <span class="badge badge-danger">KHUSUS MASTER ADMIN</span>
        <button class="btn btn-ghost btn-sm" @click="fetchMetrics">Segarkan</button>
      </div>
    </div>

    <!-- RUNTIME TELEMETRI KARTU -->
    <div class="stats-grid">
      <div class="stat-card" style="border-left: 3px solid var(--blue)">
        <div class="label">CPU Pusat</div>
        <div class="value mono">{{ cpuPercent }}%</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--green)">
        <div class="label">RAM Server Pusat</div>
        <div class="value mono">{{ memPercent }}%</div>
        <div style="font-size:10px;color:var(--dim);margin-top:4px">{{ memStr }}</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--purple)">
        <div class="label">Kapasitas Basis Data</div>
        <div class="value mono">{{ dbTotalSize }}</div>
        <div style="font-size:10px;color:var(--dim);margin-top:4px">{{ dbTotalRows }} baris catatan</div>
      </div>
    </div>

    <!-- KARTU TABEL DATA BASE STATISTIK -->
    <div class="card">
      <div class="card-header">
        <div>
          <h3>Alokasi Penyimpanan Basis Data (MariaDB)</h3>
          <div style="font-size:11.5px;color:var(--dim)">Statistik ukuran tabel telemetri dan audit.</div>
        </div>
        <button class="btn btn-primary btn-sm" @click="optimizeDatabase" :disabled="loadingOpt">
          {{ loadingOpt ? 'Mengoptimasi...' : 'Optimasi Basis Data (1-Click)' }}
        </button>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nama Tabel</th>
              <th>Jumlah Baris</th>
              <th>Ukuran Data</th>
              <th>Ukuran Indeks</th>
              <th>Total Ukuran</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in dbTables" :key="t.table_name">
              <td><strong class="mono" style="color:var(--text-bright)">{{ t.table_name }}</strong></td>
              <td class="mono">{{ t.table_rows ? t.table_rows.toLocaleString() : '0' }}</td>
              <td class="mono">{{ t.data_size_str || '-' }}</td>
              <td class="mono">{{ t.index_size_str || '-' }}</td>
              <td class="mono" style="font-weight:700">{{ t.total_size_str || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { api } from '@/api';

const cpuPercent = ref('0.0');
const memPercent = ref('0.0');
const memStr = ref('-');
const dbTotalSize = ref('-');
const dbTotalRows = ref('0');
const dbTables = ref([]);
const loadingOpt = ref(false);

async function fetchMetrics() {
  try {
    const data = await api.get('/api/master-control/metrics');
    if (data) {
      if (data.cpu != null) cpuPercent.value = Number(data.cpu).toFixed(1);
      if (data.mem != null) memPercent.value = Number(data.mem.percent || 0).toFixed(1);
      if (data.mem) memStr.value = `${data.mem.used_str || '-'} / ${data.mem.total_str || '-'}`;
      if (data.db_stats) {
        dbTotalSize.value = data.db_stats.total_size_str || '-';
        dbTotalRows.value = (data.db_stats.total_rows || 0).toLocaleString();
        dbTables.value = data.db_stats.tables || [];
      }
    }
  } catch (e) {
    // fallback
  }
}

async function optimizeDatabase() {
  if (!confirm('Jalankan proses OPTIMIZE TABLE pada seluruh tabel database?')) return;
  loadingOpt.value = true;
  try {
    const res = await api.post('/api/master-control/optimize-db', {});
    alert(res.message || 'Optimasi basis data selesai!');
    await fetchMetrics();
  } catch (e) {
    alert(e.message);
  } finally {
    loadingOpt.value = false;
  }
}

onMounted(() => {
  fetchMetrics();
});
</script>
