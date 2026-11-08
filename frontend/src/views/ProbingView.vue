<template>
  <div>
    <div class="topbar">
      <h2>Pemantauan Endpoint &amp; Jaringan</h2>
      <button class="btn btn-primary btn-sm" @click="showAddModal = true">+ Tambah Endpoint</button>
    </div>

    <!-- KPI STRIP -->
    <div class="stats-grid">
      <div class="stat-card" style="border-left: 3px solid var(--blue)">
        <div class="label">Total Endpoint</div>
        <div class="value">{{ probes.length }}</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--green)">
        <div class="label">Normal (UP)</div>
        <div class="value" style="color:var(--green)">{{ upCount }}</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--red)">
        <div class="label">Bermasalah (DOWN)</div>
        <div class="value" style="color:var(--red)">{{ downCount }}</div>
      </div>
      <div class="stat-card" style="border-left: 3px solid var(--purple)">
        <div class="label">Rata-rata Latensi</div>
        <div class="value mono">{{ avgLatency }} <span style="font-size:12px;color:var(--dim)">ms</span></div>
      </div>
    </div>

    <!-- TABEL ENDPOINT TERPANTAU -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table style="min-width:960px">
          <thead>
            <tr>
              <th class="sticky-left" style="width:90px;text-align:center">Status</th>
              <th style="min-width:240px">Nama &amp; Target</th>
              <th style="width:140px">Server Terkait</th>
              <th style="width:140px">Latensi &amp; Respons</th>
              <th style="width:130px">Ketersediaan</th>
              <th class="col-act" style="width:100px">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="probes.length === 0">
              <td colspan="6" style="text-align:center;padding:36px;color:var(--dim)">Belum ada endpoint yang dipantau.</td>
            </tr>
            <tr v-for="p in probes" :key="p.id">
              <td class="sticky-left" style="text-align:center">
                <span :class="['badge', p.status === 'up' ? 'badge-up' : 'badge-down']">
                  {{ (p.status || 'UP').toUpperCase() }}
                </span>
              </td>
              <td>
                <div style="font-weight:700;color:var(--text-bright)">{{ p.name }}</div>
                <div class="mono" style="font-size:10.5px;color:var(--dim)">{{ p.target }}</div>
              </td>
              <td class="mono" style="font-size:11px">{{ p.server_hostname || 'Mandiri' }}</td>
              <td class="mono" style="font-size:11px">
                <span v-if="p.last_latency_ms != null" style="font-weight:700">{{ p.last_latency_ms.toFixed(1) }} ms</span>
                <span v-else style="color:var(--dim)">-</span>
                <span v-if="p.last_status_code" class="badge badge-muted" style="margin-left:4px">{{ p.last_status_code }}</span>
              </td>
              <td class="mono" style="font-size:11px">{{ (p.uptime_24h || 100).toFixed(1) }}%</td>
              <td class="col-act">
                <div style="display:flex;gap:4px;justify-content:center">
                  <button class="btn btn-ghost btn-sm" @click="checkProbeNow(p)" style="padding:2px 6px;font-size:10px" title="Periksa Sekarang">&#9654;</button>
                  <button class="btn btn-danger btn-sm" @click="deleteProbe(p)" style="padding:2px 6px;font-size:10px">&#10005;</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- MODAL TAMBAH ENDPOINT TERKUNCI VIEWPORT -->
    <div v-if="showAddModal" class="modal-backdrop" @click.self="showAddModal = false">
      <div class="modal-window">
        <div class="modal-header">
          <h3>Tambah Endpoint Pantau Baru</h3>
          <button class="btn btn-ghost btn-sm" @click="showAddModal = false">&#10005;</button>
        </div>
        <form @submit.prevent="submitAddProbe">
          <div class="modal-body">
            <div class="filter-group">
              <label class="filter-label">Tipe Pemantauan</label>
              <select v-model="formProbe.type" class="filter-select">
                <option value="http">Web (HTTP / HTTPS)</option>
                <option value="ping">Ping Jaringan (ICMP)</option>
                <option value="tcp">Port Layanan (TCP)</option>
              </select>
            </div>
            <div class="filter-group">
              <label class="filter-label">Nama Endpoint *</label>
              <input type="text" v-model="formProbe.name" class="filter-input" required placeholder="Contoh: Website Resmi, API Gateway">
            </div>
            <div class="filter-group">
              <label class="filter-label">Target URL / Host / IP *</label>
              <input type="text" v-model="formProbe.target" class="filter-input" required placeholder="Contoh: https://barrukab.go.id atau 192.168.1.1">
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" @click="showAddModal = false">Batal</button>
            <button type="submit" class="btn btn-primary" :disabled="loadingSubmit">Simpan Endpoint</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { api } from '@/api';

const probes = ref([]);
const showAddModal = ref(false);
const loadingSubmit = ref(false);

const formProbe = ref({
  type: 'http',
  name: '',
  target: '',
});

const upCount = computed(() => probes.value.filter(p => p.status === 'up').length);
const downCount = computed(() => probes.value.filter(p => p.status === 'down').length);
const avgLatency = computed(() => {
  const withLat = probes.value.filter(p => p.last_latency_ms != null);
  if (!withLat.length) return '0.0';
  const sum = withLat.reduce((a, b) => a + b.last_latency_ms, 0);
  return (sum / withLat.length).toFixed(1);
});

async function fetchProbes() {
  try {
    const data = await api.get('/api/probes');
    if (data && data.probes) {
      probes.value = data.probes;
    } else if (Array.isArray(data)) {
      probes.value = data;
    }
  } catch (e) {
    // fallback
  }
}

async function submitAddProbe() {
  loadingSubmit.value = true;
  try {
    await api.post('/api/probes', formProbe.value);
    showAddModal.value = false;
    formProbe.value = { type: 'http', name: '', target: '' };
    await fetchProbes();
  } catch (e) {
    alert(e.message);
  } finally {
    loadingSubmit.value = false;
  }
}

async function checkProbeNow(p) {
  try {
    await api.post(`/api/probes/${p.id}/test`, {});
    await fetchProbes();
  } catch (e) {
    alert(e.message);
  }
}

async function deleteProbe(p) {
  if (!confirm(`Hapus pemantauan endpoint ${p.name}?`)) return;
  try {
    await api.delete(`/api/probes/${p.id}`);
    await fetchProbes();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(() => {
  fetchProbes();
});
</script>
