<template>
  <div>
    <div class="topbar">
      <h2>Jendela Pemeliharaan Terjadwal</h2>
      <button class="btn btn-primary btn-sm" @click="showAddModal = true">+ Tambah Jendela Pemeliharaan</button>
    </div>

    <!-- TABEL JENDELA PEMELIHARAAN -->
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table style="min-width:980px">
          <thead>
            <tr>
              <th style="width:115px">Status</th>
              <th style="min-width:240px">Judul &amp; Keterangan</th>
              <th style="width:160px">Cakupan Server</th>
              <th style="width:140px">Pola Jadwal</th>
              <th style="width:200px">Waktu Pelaksanaan</th>
              <th class="col-act" style="width:90px">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="windows.length === 0">
              <td colspan="6" style="text-align:center;padding:36px;color:var(--dim)">Tidak ada jadwal pemeliharaan aktif.</td>
            </tr>
            <tr v-for="w in windows" :key="w.id">
              <td>
                <span :class="['badge', w.is_active ? 'badge-warn' : 'badge-muted']">
                  {{ w.is_active ? 'SEDANG JALAN' : (w.is_past ? 'SELESAI' : 'TERJADWAL') }}
                </span>
              </td>
              <td>
                <div style="font-weight:700;color:var(--text-bright)">{{ w.title }}</div>
                <div style="font-size:10.5px;color:var(--dim)">{{ w.description || 'Tidak ada catatan SOP' }}</div>
              </td>
              <td class="mono" style="font-size:10.5px">{{ w.scope_label || 'Seluruh Server' }}</td>
              <td>
                <span class="badge badge-info" style="font-size:8px">{{ (w.schedule_type || 'once').toUpperCase() }}</span>
              </td>
              <td class="mono" style="font-size:10.5px">
                <div>{{ w.start_time_str }}</div>
                <div style="color:var(--dim)">s/d {{ w.end_time_str }}</div>
              </td>
              <td class="col-act">
                <button class="btn btn-danger btn-sm" @click="deleteWindow(w)" style="padding:2px 6px;font-size:10px">&#10005;</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- MODAL TAMBAH JENDELA TERKUNCI VIEWPORT -->
    <div v-if="showAddModal" class="modal-backdrop" @click.self="showAddModal = false">
      <div class="modal-window">
        <div class="modal-header">
          <h3>Tambah Jendela Pemeliharaan Terjadwal</h3>
          <button class="btn btn-ghost btn-sm" @click="showAddModal = false">&#10005;</button>
        </div>
        <form @submit.prevent="submitAddWindow">
          <div class="modal-body">
            <div class="filter-group">
              <label class="filter-label">Judul Pemeliharaan *</label>
              <input type="text" v-model="formMaint.title" class="filter-input" required placeholder="Contoh: Pembaruan Rutin Kernel &amp; Patch OS">
            </div>
            <div class="filter-group">
              <label class="filter-label">Deskripsi / Prosedur SOP</label>
              <input type="text" v-model="formMaint.description" class="filter-input" placeholder="Tuliskan catatan teknis...">
            </div>
            <div class="filter-group">
              <label class="filter-label">Waktu Mulai *</label>
              <input type="datetime-local" v-model="formMaint.start_time" class="filter-input" required>
            </div>
            <div class="filter-group">
              <label class="filter-label">Waktu Selesai *</label>
              <input type="datetime-local" v-model="formMaint.end_time" class="filter-input" required>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" @click="showAddModal = false">Batal</button>
            <button type="submit" class="btn btn-primary" :disabled="loadingSubmit">Simpan Jadwal</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { api } from '@/api';

const windows = ref([]);
const showAddModal = ref(false);
const loadingSubmit = ref(false);

const formMaint = ref({
  title: '',
  description: '',
  start_time: '',
  end_time: '',
});

async function fetchWindows() {
  try {
    const data = await api.get('/api/maintenance-windows');
    if (data && data.windows) {
      windows.value = data.windows;
    } else if (Array.isArray(data)) {
      windows.value = data;
    }
  } catch (e) {
    try {
      const data2 = await api.get('/api/maintenance/windows');
      if (data2 && data2.windows) windows.value = data2.windows;
      else if (Array.isArray(data2)) windows.value = data2;
    } catch (e2) {}
  }
}

async function submitAddWindow() {
  loadingSubmit.value = true;
  try {
    await api.post('/api/maintenance-windows', formMaint.value);
    showAddModal.value = false;
    formMaint.value = { title: '', description: '', start_time: '', end_time: '' };
    await fetchWindows();
  } catch (e) {
    alert(e.message);
  } finally {
    loadingSubmit.value = false;
  }
}

async function deleteWindow(w) {
  if (!confirm(`Hapus jadwal ${w.title}?`)) return;
  try {
    await api.delete(`/api/maintenance-windows/${w.id}`);
    await fetchWindows();
  } catch (e) {
    alert(e.message);
  }
}

onMounted(() => {
  fetchWindows();
});
</script>
