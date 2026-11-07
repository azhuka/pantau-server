<template>
  <div class="space-y-4">
    <div class="bg-noc-card border border-noc-border p-3.5 rounded-lg flex flex-col sm:flex-row items-center justify-between gap-3">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Manajemen Pengguna & Hak Akses Operator</span>
          <span class="noc-badge noc-badge-cyan">{{ users.length }} pengguna</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Kelola akun operator NOC, hak akses terminal web, kendali APT, dan manajemen file</p>
      </div>

      <button @click="showAddModal = true" class="noc-btn noc-btn-primary py-1.5 px-3">
        + Tambah Pengguna
      </button>
    </div>

    <!-- Users Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-12 text-center">Status</th>
            <th>Nama Pengguna</th>
            <th>Peran (Role)</th>
            <th>Terminal Shell</th>
            <th>Kendali APT</th>
            <th>File Manager</th>
            <th class="w-32 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="text-center">
              <span
                class="inline-block w-2.5 h-2.5 rounded-full"
                :class="u.is_active ? 'bg-emerald-400' : 'bg-rose-500'"
              ></span>
            </td>
            <td class="font-bold text-xs text-noc-text">{{ u.username }}</td>
            <td class="font-mono text-xs text-noc-cyan capitalize">{{ u.role?.replace('_', ' ') }}</td>
            <td>
              <span class="noc-badge" :class="u.permissions?.can_terminal ? 'noc-badge-green' : 'noc-badge-gray'">
                {{ u.permissions?.can_terminal ? 'Aktif' : 'Terkunci' }}
              </span>
            </td>
            <td>
              <span class="noc-badge" :class="u.permissions?.can_apt ? 'noc-badge-green' : 'noc-badge-gray'">
                {{ u.permissions?.can_apt ? 'Aktif' : 'Terkunci' }}
              </span>
            </td>
            <td>
              <span class="noc-badge" :class="u.permissions?.can_files ? 'noc-badge-green' : 'noc-badge-gray'">
                {{ u.permissions?.can_files ? 'Aktif' : 'Terkunci' }}
              </span>
            </td>
            <td class="text-right space-x-1">
              <button
                @click="toggleActive(u)"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]"
              >
                {{ u.is_active ? 'Nonaktifkan' : 'Aktifkan' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal: Tambah Pengguna -->
    <div v-if="showAddModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
      <div class="w-full max-w-sm noc-card p-5 border-noc-border shadow-2xl relative">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border mb-4">
          <h2 class="text-sm font-bold uppercase tracking-tight text-noc-text">Tambah Pengguna Baru</h2>
          <button @click="showAddModal = false" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <form @submit.prevent="handleAddUser" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Pengguna</label>
            <input
              v-model="newUser.username"
              type="text"
              required
              placeholder="operator-1"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Kata Sandi</label>
            <input
              v-model="newUser.password"
              type="password"
              required
              placeholder="••••••••••••"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Peran Pengguna</label>
            <select
              v-model="newUser.role"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            >
              <option value="operator">Operator NOC</option>
              <option value="viewer">Pengamat (Viewer / Read-Only)</option>
              <option value="master_admin">Master Administrator</option>
            </select>
          </div>

          <div class="pt-3 border-t border-noc-border flex justify-end gap-2">
            <button type="button" @click="showAddModal = false" class="noc-btn noc-btn-secondary">
              Batal
            </button>
            <button type="submit" class="noc-btn noc-btn-primary">
              Simpan Pengguna
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const users = ref([])
const showAddModal = ref(false)
const newUser = ref({ username: '', password: '', role: 'operator' })

async function fetchUsers() {
  try {
    const data = await api.get('/api/users')
    if (data && Array.isArray(data.users)) {
      users.value = data.users
    } else {
      // Mock / fallback
      users.value = [
        { id: 1, username: 'admin', role: 'master_admin', is_active: 1, permissions: { can_terminal: true, can_apt: true, can_files: true } },
      ]
    }
  } catch (err) {
    users.value = [
      { id: 1, username: 'admin', role: 'master_admin', is_active: 1, permissions: { can_terminal: true, can_apt: true, can_files: true } },
    ]
  }
}

async function handleAddUser() {
  try {
    const formData = new FormData()
    formData.append('username', newUser.value.username)
    formData.append('password', newUser.value.password)
    formData.append('role', newUser.value.role)
    await api.post('/users/add', formData)
    showAddModal.value = false
    newUser.value = { username: '', password: '', role: 'operator' }
    await fetchUsers()
  } catch (err) {
    alert('Gagal menambah pengguna: ' + err.message)
  }
}

async function toggleActive(u) {
  try {
    await api.post(`/users/${u.id}/toggle-active`)
    await fetchUsers()
  } catch (err) {
    alert('Gagal mengubah status: ' + err.message)
  }
}

onMounted(() => {
  fetchUsers()
})
</script>
