<template>
  <div>
    <div class="topbar">
      <h2>Riwayat Tindakan Pengguna</h2>
      <button class="btn btn-ghost btn-sm" @click="fetchAudit">Perbarui</button>
    </div>

    <!-- PANEL FILTER ALAMI (ZERO DOUBLE SCROLLBAR) -->
    <div class="filter-panel">
      <div class="filter-group">
        <label class="filter-label">Pengguna</label>
        <select v-model="filterUser" class="filter-select">
          <option value="">Semua Pengguna</option>
          <option v-for="u in users" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">Status</label>
        <select v-model="filterStatus" class="filter-select">
          <option value="">Semua Status</option>
          <option value="SUCCESS">Berhasil</option>
          <option value="FAILED">Gagal</option>
        </select>
      </div>

      <div class="filter-group" style="flex:1;min-width:200px">
        <label class="filter-label">Cari Audit</label>
        <input type="text" v-model="searchQuery" class="filter-input" placeholder="Cari aksi, target, atau hasil...">
      </div>

      <div style="display:flex;gap:4px;align-self:flex-end">
        <button v-for="p in ['today', '24h', '7d', 'all']" :key="p"
                :class="['btn', 'btn-sm', period === p ? 'btn-primary' : 'btn-ghost']"
                @click="period = p; fetchAudit()">
          {{ p === 'today' ? 'Hari Ini' : (p === '24h' ? '24 Jam' : (p === '7d' ? '7 Hari' : 'Semua')) }}
        </button>
      </div>
    </div>

    <!-- TABEL RIWAYAT AUDIT -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table style="min-width:960px">
          <thead>
            <tr>
              <th style="width:145px">Waktu</th>
              <th style="width:130px">Pengguna</th>
              <th style="width:120px">Server</th>
              <th style="width:130px">Tindakan</th>
              <th style="min-width:180px">Target</th>
              <th style="width:95px;text-align:center">Status</th>
              <th style="min-width:220px">Hasil / Respons</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredLogs.length === 0">
              <td colspan="7" style="text-align:center;padding:36px;color:var(--dim)">Belum ada catatan riwayat audit.</td>
            </tr>
            <tr v-for="r in filteredLogs" :key="r.id">
              <td class="mono" style="font-size:10.5px">{{ r.time_str || '-' }}</td>
              <td><strong class="mono" style="color:var(--text-bright)">{{ r.user }}</strong></td>
              <td class="mono">{{ r.server || '-' }}</td>
              <td><span class="badge badge-info" style="font-size:8px">{{ r.action }}</span></td>
              <td class="mono" style="font-size:10.5px">{{ r.target || '-' }}</td>
              <td style="text-align:center">
                <span :class="['badge', r.status === 'SUCCESS' ? 'badge-up' : 'badge-down']">
                  {{ r.status === 'SUCCESS' ? 'BERHASIL' : 'GAGAL' }}
                </span>
              </td>
              <td style="font-size:11px;color:var(--dim);line-height:1.35">{{ r.result || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { api } from '@/api';

const logs = ref([]);
const users = ref([]);
const filterUser = ref('');
const filterStatus = ref('');
const searchQuery = ref('');
const period = ref('24h');

const filteredLogs = computed(() => {
  return logs.value.filter(l => {
    if (filterUser.value && l.user !== filterUser.value) return false;
    if (filterStatus.value && l.status !== filterStatus.value) return false;
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase();
      const match = (l.action && l.action.toLowerCase().includes(q)) ||
                    (l.target && l.target.toLowerCase().includes(q)) ||
                    (l.result && l.result.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });
});

async function fetchAudit() {
  try {
    const data = await api.get(`/api/audit?period=${period.value}`);
    if (data && data.rows) {
      logs.value = data.rows;
      users.value = data.users || [];
    } else if (Array.isArray(data)) {
      logs.value = data;
    }
  } catch (e) {
    // fallback
  }
}

onMounted(() => {
  fetchAudit();
});
</script>
