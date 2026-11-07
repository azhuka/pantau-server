<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row items-center justify-between gap-3 bg-noc-card border border-noc-border p-3 rounded-lg">
      <div>
        <h1 class="text-base font-bold text-noc-text uppercase tracking-tight flex items-center gap-2">
          <span>Pemantauan Synthetic Probing</span>
          <span class="noc-badge noc-badge-cyan">{{ targets.length }} target</span>
        </h1>
        <p class="text-xs text-noc-muted mt-0.5">Pemantauan proaktif berbasis HTTP/S, ICMP Ping, dan TCP Port Handshake tanpa agen</p>
      </div>

      <button @click="showAddModal = true" class="noc-btn noc-btn-primary py-1.5 px-3">
        + Tambah Target Pantau
      </button>
    </div>

    <!-- Targets Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-12 text-center">Status</th>
            <th>Nama Target</th>
            <th class="w-16">Tipe</th>
            <th>URL / Host Target</th>
            <th>Latensi Terakhir</th>
            <th>SLA 24 Jam</th>
            <th>SLA 30 Hari</th>
            <th>Interval</th>
            <th class="w-32 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in targets" :key="t.id">
            <td class="text-center">
              <span
                class="inline-block w-2.5 h-2.5 rounded-full"
                :class="t.status === 'up' ? 'bg-emerald-400' : 'bg-rose-500'"
              ></span>
            </td>
            <td class="font-bold text-xs text-noc-text">{{ t.name }}</td>
            <td class="font-mono text-xs uppercase font-bold text-noc-cyan">{{ t.type }}</td>
            <td class="font-mono text-xs text-noc-dim truncate max-w-xs">{{ t.target }}</td>
            <td class="font-mono text-xs">
              <span :class="t.last_latency_ms > 500 ? 'text-amber-400 font-bold' : 'text-emerald-400'">
                {{ t.last_latency_ms !== null ? `${t.last_latency_ms} ms` : '—' }}
              </span>
            </td>
            <td class="font-mono text-xs font-semibold">{{ t.uptime_24h ? `${t.uptime_24h}%` : '100%' }}</td>
            <td class="font-mono text-xs text-noc-muted">{{ t.uptime_30d ? `${t.uptime_30d}%` : '100%' }}</td>
            <td class="font-mono text-[11px] text-noc-muted">{{ t.interval_seconds }}s</td>
            <td class="text-right space-x-1">
              <button
                @click="testTarget(t)"
                :disabled="testing === t.id"
                class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]"
              >
                Uji Coba
              </button>
              <button
                @click="deleteTarget(t)"
                class="noc-btn noc-btn-secondary py-0.5 px-1.5 text-[10px] text-rose-400"
              >
                ✕
              </button>
            </td>
          </tr>
          <tr v-if="targets.length === 0">
            <td colspan="9" class="text-center py-8 text-noc-muted">Belum ada target synthetic probing yang didaftarkan</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal: Tambah Target -->
    <div v-if="showAddModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
      <div class="w-full max-w-md noc-card p-5 border-noc-border shadow-2xl relative">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border mb-4">
          <h2 class="text-sm font-bold uppercase tracking-tight text-noc-text">Daftarkan Target Probing Baru</h2>
          <button @click="showAddModal = false" class="text-noc-muted hover:text-noc-text text-base">✕</button>
        </div>

        <form @submit.prevent="handleAddTarget" class="space-y-3 text-xs">
          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Nama Target</label>
            <input
              v-model="newTarget.name"
              type="text"
              required
              placeholder="contoh: Web API Gateway Pusat"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Tipe Probing</label>
            <select
              v-model="newTarget.type"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            >
              <option value="http">HTTP / HTTPS URL</option>
              <option value="icmp">ICMP Ping</option>
              <option value="tcp">TCP Port Handshake</option>
            </select>
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Target (URL / Hostname / IP)</label>
            <input
              v-model="newTarget.target"
              type="text"
              required
              placeholder="https://api.domain.com atau 1.1.1.1"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div v-if="newTarget.type === 'tcp'">
            <label class="block text-[11px] font-semibold text-noc-dim uppercase mb-1">Port TCP</label>
            <input
              v-model.number="newTarget.port"
              type="number"
              required
              min="1"
              max="65535"
              placeholder="3306"
              class="w-full px-3 py-1.5 bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan"
            />
          </div>

          <div class="pt-3 border-t border-noc-border flex justify-end gap-2">
            <button type="button" @click="showAddModal = false" class="noc-btn noc-btn-secondary">
              Batal
            </button>
            <button type="submit" class="noc-btn noc-btn-primary">
              Simpan Target
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

const targets = ref([])
const showAddModal = ref(false)
const testing = ref(null)
const newTarget = ref({ name: '', type: 'http', target: '', port: null, interval_seconds: 30 })

async function fetchTargets() {
  try {
    const data = await api.get('/api/probes')
    targets.value = data?.targets || []
  } catch (err) {
    console.error('Gagal mengambil target probing:', err)
  }
}

async function handleAddTarget() {
  try {
    await api.post('/api/probes', newTarget.value)
    showAddModal.value = false
    newTarget.value = { name: '', type: 'http', target: '', port: null, interval_seconds: 30 }
    await fetchTargets()
  } catch (err) {
    alert('Gagal menambah target: ' + err.message)
  }
}

async function testTarget(target) {
  testing.value = target.id
  try {
    const res = await api.post(`/api/probes/${target.id}/test`)
    alert(`Hasil Uji Coba: ${res.status.toUpperCase()} (${res.latency_ms} ms)`)
    await fetchTargets()
  } catch (err) {
    alert('Uji coba gagal: ' + err.message)
  } finally {
    testing.value = null
  }
}

async function deleteTarget(target) {
  if (!confirm(`Hapus target probing ${target.name}?`)) return
  try {
    await api.delete(`/api/probes/${target.id}`)
    await fetchTargets()
  } catch (err) {
    alert('Gagal menghapus target: ' + err.message)
  }
}

onMounted(() => {
  fetchTargets()
})
</script>
