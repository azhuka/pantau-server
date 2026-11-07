<template>
  <div class="space-y-4">
    <!-- Header & Action Bar -->
    <div class="flex flex-col sm:flex-row items-center justify-between gap-3 bg-noc-card border border-noc-border p-3 rounded-lg">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Armada Server Terpantau</span>
          <span class="noc-badge noc-badge-cyan">{{ serverStore.servers.length }} node</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Kelola seluruh node Linux yang terhubung ke dashboard Pantau</p>
      </div>

      <div class="flex items-center gap-2 w-full sm:w-auto">
        <input
          v-model="serverStore.searchQuery"
          type="text"
          placeholder="Cari server..."
          class="w-full sm:w-60 px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-xs text-noc-text focus:outline-none focus:border-noc-cyan"
        />
        <button
          @click="showAddModal = true"
          class="noc-btn noc-btn-primary whitespace-nowrap py-1.5 px-3"
        >
          + Tambah Server
        </button>
      </div>
    </div>

    <!-- Servers Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-12 text-center">Status</th>
            <th>Nama Host</th>
            <th>Alamat IP</th>
            <th>Distro Linux</th>
            <th>Beban CPU</th>
            <th>RAM</th>
            <th>Disk Root</th>
            <th>Versi Agen</th>
            <th>Terakhir Melapor</th>
            <th class="w-32 text-right">Kelola</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="srv in serverStore.filteredServers" :key="srv.id">
            <td class="text-center">
              <span
                class="inline-block w-2.5 h-2.5 rounded-full"
                :class="{
                  'bg-emerald-400': srv.status === 'up' && !srv.is_maintenance,
                  'bg-rose-500': srv.status === 'down',
                  'bg-amber-400': srv.status === 'stale',
                  'bg-purple-400': srv.is_maintenance,
                }"
              ></span>
            </td>
            <td class="font-bold text-xs">
              <router-link :to="`/servers/${srv.id}`" class="text-noc-cyan hover:underline">
                {{ srv.hostname }}
              </router-link>
            </td>
            <td class="font-mono text-xs text-noc-dim">{{ srv.ip_address || '—' }}</td>
            <td class="text-xs text-noc-muted truncate max-w-[160px]">{{ srv.os_label || 'Linux' }}</td>
            <td class="font-mono text-xs">
              {{ srv.cpu_pct !== undefined && srv.cpu_pct !== null ? `${Math.round(srv.cpu_pct)}%` : '—' }}
            </td>
            <td class="font-mono text-xs">
              {{ srv.ram_pct !== undefined && srv.ram_pct !== null ? `${Math.round(srv.ram_pct)}%` : '—' }}
            </td>
            <td class="font-mono text-xs">
              {{ srv.disk_pct !== undefined && srv.disk_pct !== null ? `${Math.round(srv.disk_pct)}%` : '—' }}
            </td>
            <td class="font-mono text-xs text-noc-muted">v{{ srv.agent_version || '—' }}</td>
            <td class="font-mono text-xs text-noc-muted">{{ srv.last_seen_str || 'Baru saja' }}</td>
            <td class="text-right space-x-1">
              <router-link :to="`/servers/${srv.id}`" class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]">
                Detail
              </router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal: Tambah Server -->
    <div v-if="showAddModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div class="w-full max-w-lg noc-card p-5 border-noc-border shadow-2xl relative">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border mb-4">
          <h2 class="text-sm font-bold uppercase tracking-tight text-noc-text">Daftarkan Node Server Baru</h2>
          <button @click="showAddModal = false" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <form @submit.prevent="handleAddServer" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Host (Hostname)</label>
            <input
              v-model="newServer.hostname"
              type="text"
              required
              placeholder="contoh: srv-db-master"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Alamat IP (Opsional)</label>
            <input
              v-model="newServer.ip_address"
              type="text"
              placeholder="contoh: 192.168.1.100"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div class="pt-3 border-t border-noc-border flex justify-end gap-2">
            <button type="button" @click="showAddModal = false" class="noc-btn noc-btn-secondary">
              Batal
            </button>
            <button type="submit" :disabled="creating" class="noc-btn noc-btn-primary">
              {{ creating ? 'Menyimpan...' : 'Daftarkan Server' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useServerStore } from '@/stores/servers'
import { api } from '@/api/client'

const serverStore = useServerStore()
const showAddModal = ref(false)
const creating = ref(false)
const newServer = ref({ hostname: '', ip_address: '' })

async function handleAddServer() {
  creating.value = true
  try {
    const formData = new FormData()
    formData.append('hostname', newServer.value.hostname)
    if (newServer.value.ip_address) {
      formData.append('ip_address', newServer.value.ip_address)
    }
    await api.post('/servers/add', formData)
    showAddModal.value = false
    newServer.value = { hostname: '', ip_address: '' }
    await serverStore.fetchServers()
  } catch (err) {
    alert('Gagal mendaftarkan server: ' + err.message)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  serverStore.startPolling(5000)
})

onUnmounted(() => {
  serverStore.stopPolling()
})
</script>
