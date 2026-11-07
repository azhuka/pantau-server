<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between bg-noc-card border border-noc-border p-3 rounded-lg">
      <div>
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-text flex items-center gap-2">
          <span>Layanan Daemon & Port Terpantau</span>
          <span class="noc-badge noc-badge-cyan">{{ services.length }} layanan</span>
        </h3>
        <p class="text-[11px] text-noc-muted mt-0.5">Pemantauan ketersediaan proses sistem dan port aplikasi lokal</p>
      </div>

      <button @click="showAddModal = true" class="noc-btn noc-btn-primary py-1 px-2.5 text-xs">
        + Tambah Layanan
      </button>
    </div>

    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-12 text-center">Status</th>
            <th>Nama Layanan</th>
            <th>Port</th>
            <th>Nama Proses / Unit Systemd</th>
            <th>Latensi Port</th>
            <th>Koneksi Aktif</th>
            <th>Penting (Core)</th>
            <th class="w-48 text-right">Aksi Operator</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="svc in services" :key="svc.id">
            <td class="text-center">
              <span
                class="inline-block w-2.5 h-2.5 rounded-full"
                :class="svc.status === 'up' ? 'bg-emerald-400' : 'bg-rose-500'"
              ></span>
            </td>
            <td class="font-bold text-xs text-noc-text">
              <div class="flex items-center gap-1.5">
                <span>{{ svc.service_name }}</span>
                <span v-if="svc.is_ignored" class="noc-badge noc-badge-gray text-[9px]">Diabaikan</span>
              </div>
            </td>
            <td class="font-mono text-xs text-noc-cyan">{{ svc.port || '—' }}</td>
            <td class="font-mono text-xs text-noc-dim">{{ svc.process_name || svc.service_name }}</td>
            <td class="font-mono text-xs">{{ svc.response_time_ms ? `${svc.response_time_ms} ms` : '—' }}</td>
            <td class="font-mono text-xs">{{ svc.active_connections !== undefined ? svc.active_connections : '—' }}</td>
            <td>
              <button
                @click="toggleCore(svc)"
                class="noc-badge cursor-pointer"
                :class="svc.is_core ? 'noc-badge-amber' : 'noc-badge-gray'"
                title="Klik untuk mengubah prioritas"
              >
                {{ svc.is_core ? '★ INTI' : 'Sekunder' }}
              </button>
            </td>
            <td class="text-right space-x-1">
              <button
                @click="triggerAction(svc, 'restart')"
                :disabled="acting === svc.id"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]"
                title="Restart Layanan via systemd"
              >
                Restart
              </button>
              <button
                v-if="svc.status === 'up'"
                @click="triggerAction(svc, 'stop')"
                :disabled="acting === svc.id"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-rose-400"
                title="Matikan Layanan"
              >
                Stop
              </button>
              <button
                v-else
                @click="triggerAction(svc, 'start')"
                :disabled="acting === svc.id"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-emerald-400"
                title="Nyalakan Layanan"
              >
                Start
              </button>
              <button
                @click="deleteService(svc)"
                class="noc-btn noc-btn-secondary py-0.5 px-1.5 text-[10px] text-noc-muted hover:text-rose-400"
                title="Hapus dari daftar pantau"
              >
                ✕
              </button>
            </td>
          </tr>
          <tr v-if="services.length === 0">
            <td colspan="8" class="text-center py-6 text-noc-muted">Belum ada layanan yang didaftarkan untuk node ini</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal Tambah Layanan -->
    <div v-if="showAddModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div class="w-full max-w-md noc-card p-5 border-noc-border shadow-2xl relative">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border mb-4">
          <h2 class="text-sm font-bold uppercase tracking-tight text-noc-text">Tambah Layanan Pantau</h2>
          <button @click="showAddModal = false" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <form @submit.prevent="handleAddService" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Layanan</label>
            <input
              v-model="newSvc.service_name"
              type="text"
              required
              placeholder="contoh: nginx / mysql / redis"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Port Listening</label>
            <input
              v-model.number="newSvc.port"
              type="number"
              required
              min="1"
              max="65535"
              placeholder="contoh: 80, 443, 3306"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Proses / Unit Systemd</label>
            <input
              v-model="newSvc.process_name"
              type="text"
              placeholder="contoh: nginx (opsional jika sama)"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div class="pt-3 border-t border-noc-border flex justify-end gap-2">
            <button type="button" @click="showAddModal = false" class="noc-btn noc-btn-secondary">
              Batal
            </button>
            <button type="submit" class="noc-btn noc-btn-primary">
              Simpan Layanan
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
  services: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['refresh'])
const acting = ref(null)
const showAddModal = ref(false)
const newSvc = ref({ service_name: '', port: null, process_name: '' })

async function triggerAction(svc, action) {
  if (!confirm(`Konfirmasi eksekusi ${action.toUpperCase()} pada layanan ${svc.service_name}?`)) return
  acting.value = svc.id
  try {
    await api.post(`/servers/${props.serverId}/services/${svc.id}/${action}`)
    emit('refresh')
  } catch (err) {
    alert(`Gagal mengeksekusi ${action}: ` + err.message)
  } finally {
    acting.value = null
  }
}

async function toggleCore(svc) {
  try {
    await api.post(`/servers/${props.serverId}/services/${svc.id}/toggle-core`)
    emit('refresh')
  } catch (err) {
    alert('Gagal mengubah prioritas layanan: ' + err.message)
  }
}

async function deleteService(svc) {
  if (!confirm(`Hapus pemantauan untuk layanan ${svc.service_name}?`)) return
  try {
    await api.post(`/servers/${props.serverId}/services/${svc.id}/delete`)
    emit('refresh')
  } catch (err) {
    alert('Gagal menghapus layanan: ' + err.message)
  }
}

async function handleAddService() {
  try {
    const formData = new FormData()
    formData.append('service_name', newSvc.value.service_name)
    formData.append('port', newSvc.value.port)
    if (newSvc.value.process_name) {
      formData.append('process_name', newSvc.value.process_name)
    }
    await api.post(`/servers/${props.serverId}/services/add`, formData)
    showAddModal.value = false
    newSvc.value = { service_name: '', port: null, process_name: '' }
    emit('refresh')
  } catch (err) {
    alert('Gagal menambah layanan: ' + err.message)
  }
}
</script>
