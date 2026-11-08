<template>
  <div>
    <div class="topbar">
      <h2>Daftar Server</h2>
      <button class="btn btn-primary btn-sm" @click="showAddModal = true">+ Tambah Server</button>
    </div>

    <!-- FILTER PANEL PRESIISI TINGGI NOC -->
    <div class="filter-panel">
      <div class="filter-group">
        <label class="filter-label">Grup</label>
        <select v-model="filterGroup" class="filter-select">
          <option value="">Semua Grup</option>
          <option v-for="g in groups" :key="g" :value="g">{{ g }}</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">Status</label>
        <select v-model="filterStatus" class="filter-select">
          <option value="">Semua Status</option>
          <option value="online">Online</option>
          <option value="offline">Offline</option>
        </select>
      </div>

      <div class="filter-group" style="flex:1;min-width:200px">
        <label class="filter-label">Cari Server</label>
        <input type="text" v-model="searchQuery" class="filter-input" placeholder="Cari nama, IP, OS, spesifikasi...">
      </div>

      <button class="btn btn-ghost btn-sm" @click="resetFilter" style="height:32px">Reset</button>
    </div>

    <!-- KARTU TABEL SERVER -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky-left" style="min-width:180px">Server</th>
              <th style="min-width:120px">IP &amp; Interface</th>
              <th style="min-width:130px">Platform &amp; Mesin</th>
              <th style="min-width:130px">Sistem Operasi</th>
              <th style="min-width:110px">Prosesor</th>
              <th style="min-width:90px">Memori</th>
              <th style="min-width:90px">Disk</th>
              <th style="min-width:85px">Uptime</th>
              <th style="width:75px;text-align:center">Status</th>
              <th class="col-act" style="width:90px">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredServers.length === 0">
              <td colspan="10" style="text-align:center;padding:36px;color:var(--dim)">Tidak ada data server yang cocok.</td>
            </tr>
            <tr v-for="s in filteredServers" :key="s.id">
              <td class="sticky-left">
                <div style="display:flex;align-items:center;gap:6px">
                  <span :class="['dot', s.is_online ? 'up' : 'down']"></span>
                  <strong style="color:var(--text-heading)">{{ s.hostname }}</strong>
                  <span v-if="s.group_name" class="badge badge-muted" style="font-size:7.5px;padding:0 4px">{{ s.group_name }}</span>
                </div>
              </td>
              <td class="mono" style="font-size:10.5px">
                <div>{{ s.ip_address }}</div>
                <div style="color:var(--dim);font-size:9.5px">{{ s.interface || 'eth0' }}</div>
              </td>
              <td>
                <span class="badge badge-info" style="font-size:8px">{{ s.platform || 'LXC' }}</span>
                <div style="font-size:9.5px;color:var(--dim);margin-top:2px">{{ s.machine_model || '-' }}</div>
              </td>
              <td style="font-size:10.5px">
                <div>{{ s.os_name || 'Ubuntu 24.04' }}</div>
                <div style="font-size:9px;color:var(--dim)" class="mono">{{ s.kernel_version || '-' }}</div>
              </td>
              <td class="mono" style="font-size:10.5px">
                <div>{{ s.cpu_model || 'Intel Xeon' }}</div>
                <div style="color:var(--dim);font-size:9.5px">{{ s.cpu_cores || 1 }} Core</div>
              </td>
              <td class="mono" style="font-size:10.5px">{{ s.mem_total_str || '-' }}</td>
              <td class="mono" style="font-size:10.5px">{{ s.disk_total_str || '-' }}</td>
              <td class="mono" style="font-size:10.5px">{{ s.uptime_str || '-' }}</td>
              <td style="text-align:center">
                <span :class="['badge', s.is_online ? 'badge-up' : 'badge-down']">{{ s.is_online ? 'ONLINE' : 'OFFLINE' }}</span>
              </td>
              <td class="col-act">
                <div style="display:flex;gap:4px;justify-content:center">
                  <button class="btn btn-ghost btn-sm" @click="viewDetails(s)" style="padding:2px 6px;font-size:10px">Detail</button>
                  <button class="btn btn-danger btn-sm" @click="deleteServer(s)" style="padding:2px 6px;font-size:10px">&#10005;</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- MODAL TAMBAH SERVER TERKUNCI VIEWPORT -->
    <div v-if="showAddModal" class="modal-backdrop" @click.self="showAddModal = false">
      <div class="modal-window">
        <div class="modal-header">
          <h3>Tambah Server Baru</h3>
          <button class="btn btn-ghost btn-sm" @click="showAddModal = false">&#10005;</button>
        </div>
        <form @submit.prevent="submitAddServer">
          <div class="modal-body">
            <div class="filter-group">
              <label class="filter-label">Nama Host (Hostname) *</label>
              <input type="text" v-model="formNew.hostname" class="filter-input" required placeholder="Contoh: web-server-01">
            </div>
            <div class="filter-group">
              <label class="filter-label">Alamat IP *</label>
              <input type="text" v-model="formNew.ip_address" class="filter-input" required placeholder="Contoh: 192.168.1.10">
            </div>
            <div class="filter-group">
              <label class="filter-label">Grup Server</label>
              <input type="text" v-model="formNew.group_name" class="filter-input" placeholder="Contoh: Produksi, Database">
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" @click="showAddModal = false">Batal</button>
            <button type="submit" class="btn btn-primary" :disabled="loadingSubmit">Simpan Server</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { api } from '@/api';

const servers = ref([]);
const groups = ref([]);
const filterGroup = ref('');
const filterStatus = ref('');
const searchQuery = ref('');
const showAddModal = ref(false);
const loadingSubmit = ref(false);

const formNew = ref({
  hostname: '',
  ip_address: '',
  group_name: '',
});

const filteredServers = computed(() => {
  return servers.value.filter(s => {
    if (filterGroup.value && s.group_name !== filterGroup.value) return false;
    if (filterStatus.value === 'online' && !s.is_online) return false;
    if (filterStatus.value === 'offline' && s.is_online) return false;
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase();
      const match = (s.hostname && s.hostname.toLowerCase().includes(q)) ||
                    (s.ip_address && s.ip_address.includes(q)) ||
                    (s.os_name && s.os_name.toLowerCase().includes(q));
      if (!match) return false;
    }
    return true;
  });
});

function resetFilter() {
  filterGroup.value = '';
  filterStatus.value = '';
  searchQuery.value = '';
}

async function fetchServers() {
  try {
    const data = await api.get('/api/servers');
    if (data && data.servers) {
      servers.value = data.servers;
      groups.value = data.groups || [];
    } else if (Array.isArray(data)) {
      servers.value = data;
    }
  } catch (e) {
    // fallback
  }
}

async function submitAddServer() {
  loadingSubmit.value = true;
  try {
    await api.post('/api/servers', formNew.value);
    showAddModal.value = false;
    formNew.value = { hostname: '', ip_address: '', group_name: '' };
    await fetchServers();
  } catch (e) {
    alert(e.message);
  } finally {
    loadingSubmit.value = false;
  }
}

async function deleteServer(s) {
  if (!confirm(`Hapus server ${s.hostname}?`)) return;
  try {
    await api.delete(`/api/servers/${s.id}`);
    await fetchServers();
  } catch (e) {
    alert(e.message);
  }
}

function viewDetails(s) {
  alert(`Rincian Server:\nHost: ${s.hostname}\nIP: ${s.ip_address}\nOS: ${s.os_name || '-'}\nUptime: ${s.uptime_str || '-'}`);
}

onMounted(() => {
  fetchServers();
});
</script>
