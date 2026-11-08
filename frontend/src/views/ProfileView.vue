<template>
  <div>
    <div class="topbar">
      <h2>Akun &amp; Manajemen Pengguna</h2>
      <button class="btn btn-primary btn-sm" @click="showAddUserModal = true">+ Tambah Akun Baru</button>
    </div>

    <!-- GRID MANAJEMEN AKUN -->
    <div style="display:grid;grid-template-columns:minmax(0, 1fr) 320px;gap:20px;align-items:start">
      <!-- TABEL PENGGUNA TERDAFTAR -->
      <div class="card" style="padding:0;overflow:hidden">
        <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
          <h3 style="font-size:14.5px;margin:0">Pengguna Terdaftar</h3>
          <span class="badge badge-info">{{ users.length }} Akun</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th class="sticky-left" style="min-width:140px">Pengguna</th>
                <th style="width:110px">Peran</th>
                <th style="width:130px">Status &amp; 2FA</th>
                <th class="col-act" style="width:100px">Tindakan</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td class="sticky-left">
                  <div style="display:flex;align-items:center;gap:6px">
                    <strong class="mono" style="color:var(--text-bright)">{{ u.username }}</strong>
                    <span v-if="u.id === currentUser.id" class="badge badge-info" style="font-size:7.5px">(Anda)</span>
                  </div>
                </td>
                <td>
                  <span :class="['badge', u.role === 'master_admin' ? 'badge-danger' : 'badge-info']">
                    {{ u.role_display || u.role }}
                  </span>
                </td>
                <td>
                  <span :class="['badge', u.is_active ? 'badge-up' : 'badge-down']">{{ u.is_active ? 'Aktif' : 'Terkunci' }}</span>
                </td>
                <td class="col-act">
                  <div style="display:flex;gap:4px;justify-content:center">
                    <button class="btn btn-ghost btn-sm" @click="editUser(u)" style="padding:2px 6px;font-size:10px">Edit</button>
                    <button v-if="u.id !== currentUser.id" class="btn btn-danger btn-sm" @click="deleteUser(u)" style="padding:2px 6px;font-size:10px">&#10005;</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- KARTU INFORMASI AKUN ANDA -->
      <div class="card">
        <div class="card-header">
          <h3>Informasi Sesi Anda</h3>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;font-size:12px">
          <div>
            <div class="filter-label">Username</div>
            <div class="mono" style="font-weight:700;font-size:14px;color:var(--text-heading);margin-top:2px">{{ currentUser.username }}</div>
          </div>
          <div>
            <div class="filter-label">Peran Sistem</div>
            <div style="margin-top:2px">
              <span class="badge badge-danger">{{ currentUser.role_display || 'MASTER ADMIN' }}</span>
            </div>
          </div>
          <div style="border-top:1px solid var(--border);padding-top:12px">
            <button class="btn btn-ghost btn-sm" @click="showPwdModal = true" style="width:100%">Ubah Kata Sandi</button>
          </div>
        </div>
      </div>
    </div>

    <!-- MODAL TAMBAH USER -->
    <div v-if="showAddUserModal" class="modal-backdrop" @click.self="showAddUserModal = false">
      <div class="modal-window">
        <div class="modal-header">
          <h3>Daftarkan Akun Pengguna Baru</h3>
          <button class="btn btn-ghost btn-sm" @click="showAddUserModal = false">&#10005;</button>
        </div>
        <form @submit.prevent="submitAddUser">
          <div class="modal-body">
            <div class="filter-group">
              <label class="filter-label">Username *</label>
              <input type="text" v-model="formUser.username" class="filter-input" required placeholder="Contoh: sysops-andi">
            </div>
            <div class="filter-group">
              <label class="filter-label">Kata Sandi Awal *</label>
              <input type="password" v-model="formUser.password" class="filter-input" required placeholder="Minimal 12 karakter">
            </div>
            <div class="filter-group">
              <label class="filter-label">Peran Akun</label>
              <select v-model="formUser.role" class="filter-select">
                <option value="operator">Operator (Hak Operasional)</option>
                <option value="viewer">Viewer (Hanya-Baca)</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-ghost" @click="showAddUserModal = false">Batal</button>
            <button type="submit" class="btn btn-primary">Simpan Akun</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { api } from '@/api';

const users = ref([]);
const currentUser = ref({ username: 'master-admin', role_display: 'MASTER ADMIN' });
const showAddUserModal = ref(false);
const showPwdModal = ref(false);

const formUser = ref({
  username: '',
  password: '',
  role: 'operator',
});

async function fetchUsers() {
  try {
    const data = await api.get('/api/users');
    if (data && data.users) users.value = data.users;
    else if (Array.isArray(data)) users.value = data;
  } catch (e) {
    // fallback
  }

  try {
    const me = await api.get('/api/auth/me');
    if (me && me.username) currentUser.value = me;
  } catch (e) {
    // fallback
  }
}

async function submitAddUser() {
  try {
    await api.post('/api/users', formUser.value);
    showAddUserModal.value = false;
    formUser.value = { username: '', password: '', role: 'operator' };
    await fetchUsers();
  } catch (e) {
    alert(e.message);
  }
}

async function deleteUser(u) {
  if (!confirm(`Hapus akun ${u.username}?`)) return;
  try {
    await api.delete(`/api/users/${u.id}`);
    await fetchUsers();
  } catch (e) {
    alert(e.message);
  }
}

function editUser(u) {
  alert(`Manajemen pengguna ${u.username}`);
}

onMounted(() => {
  fetchUsers();
});
</script>
