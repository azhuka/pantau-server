<template>
  <div>
    <div class="topbar">
      <h2>Insiden Server</h2>
      <div style="display:flex;gap:6px">
        <span class="badge badge-danger" v-if="dangerCount">{{ dangerCount }} Kritis</span>
        <span class="badge badge-warn" v-if="warnCount">{{ warnCount }} Peringatan</span>
        <span class="badge badge-up" v-if="!problems.length">0 Insiden Terbuka</span>
      </div>
    </div>

    <!-- FILTER PANEL NOC -->
    <div class="filter-panel">
      <div class="filter-group">
        <label class="filter-label">Keparahan</label>
        <select v-model="filterSev" class="filter-select">
          <option value="">Semua Keparahan</option>
          <option value="danger">Kritis</option>
          <option value="average">Gawat</option>
          <option value="warning">Peringatan</option>
          <option value="info">Info</option>
        </select>
      </div>

      <div class="filter-group" style="flex:1;min-width:220px">
        <label class="filter-label">Cari Insiden</label>
        <input type="text" v-model="searchQuery" class="filter-input" placeholder="Cari insiden, server, atau pesan error...">
      </div>

      <button class="btn btn-ghost btn-sm" @click="fetchProblems" style="height:32px">Segarkan</button>
    </div>

    <!-- KARTU TABEL INSIDEN (ANTI-COLLAPSE HERO COLUMN) -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table style="min-width:1050px">
          <thead>
            <tr>
              <th style="width:130px">Waktu Mulai</th>
              <th style="width:160px">Server</th>
              <th style="width:110px;text-align:center">Keparahan</th>
              <th style="min-width:300px">Kejadian</th>
              <th style="width:110px;text-align:right">Durasi</th>
              <th style="min-width:240px">Panduan Solusi</th>
              <th class="col-act" style="width:90px">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredProblems.length === 0">
              <td colspan="7" style="text-align:center;padding:36px;color:var(--dim)">Tidak ada insiden aktif. Semua server normal.</td>
            </tr>
            <tr v-for="p in filteredProblems" :key="p.id">
              <td class="mono" style="font-size:10.5px">{{ p.started_at_str || '-' }}</td>
              <td>
                <div style="display:flex;align-items:center;gap:6px">
                  <span :class="['dot', p.is_offline ? 'down' : 'up']"></span>
                  <strong>{{ p.hostname }}</strong>
                  <span v-if="p.group_name" class="badge badge-muted" style="font-size:7.5px">{{ p.group_name }}</span>
                </div>
              </td>
              <td style="text-align:center">
                <span :class="['badge', `badge-${p.severity === 'danger' ? 'danger' : (p.severity === 'average' ? 'warn' : 'info')}`]">
                  {{ p.severity.toUpperCase() }}
                </span>
              </td>
              <td style="line-height:1.4">
                <span style="font-weight:600;color:var(--text-bright)">{{ p.message }}</span>
                <div v-if="p.count_24h && p.count_24h > 1" style="margin-top:2px">
                  <span class="badge badge-muted" style="font-size:7.5px">kambuh {{ p.count_24h }}x</span>
                </div>
              </td>
              <td class="mono" style="text-align:right;font-size:10.5px">{{ p.durasi || '-' }}</td>
              <td style="color:var(--dim);font-size:11px;line-height:1.35">{{ p.tip || 'Periksa status layanan melalui menu Log atau rincian server.' }}</td>
              <td class="col-act">
                <div style="display:flex;gap:4px;justify-content:center">
                  <button class="btn btn-primary btn-sm" @click="resolveProblem(p)" style="padding:2px 6px;font-size:10px" title="Tandai Ditangani">&#10003;</button>
                  <button class="btn btn-ghost btn-sm" @click="ignoreProblem(p)" style="padding:2px 6px;font-size:10px" title="Abaikan Insiden">&#128065;</button>
                </div>
              </td>
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

const problems = ref([]);
const filterSev = ref('');
const searchQuery = ref('');

const dangerCount = computed(() => problems.value.filter(p => p.severity === 'danger').length);
const warnCount = computed(() => problems.value.filter(p => p.severity === 'warning' || p.severity === 'average').length);

const filteredProblems = computed(() => {
  return problems.value.filter(p => {
    if (filterSev.value && p.severity !== filterSev.value) return false;
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase();
      const match = (p.hostname && p.hostname.toLowerCase().includes(q)) ||
                    (p.message && p.message.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });
});

async function fetchProblems() {
  try {
    const data = await api.get('/api/problems');
    if (data && data.open_problems) {
      problems.value = data.open_problems;
    } else if (data && data.problems) {
      problems.value = data.problems;
    } else if (Array.isArray(data)) {
      problems.value = data;
    }
  } catch (e) {
    // fallback
  }
}

async function resolveProblem(p) {
  try {
    await api.post(`/api/problems/${p.id}/resolve`, {});
    await fetchProblems();
  } catch (e) {
    alert(e.message);
  }
}

async function ignoreProblem(p) {
  const reason = prompt('Alasan pengabaian insiden:', 'Sedang dalam pemeliharaan');
  if (reason === null) return;
  try {
    await api.post(`/api/problems/${p.id}/ignore`, { reason });
    await fetchProblems();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(() => {
  fetchProblems();
});
</script>
