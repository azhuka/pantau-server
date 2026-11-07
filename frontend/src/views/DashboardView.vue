<template>
  <div class="space-y-4">
    <!-- Top Stat Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <!-- Total Servers -->
      <div class="noc-card p-3 flex flex-col justify-between">
        <div class="text-[11px] font-semibold text-noc-dim uppercase tracking-wider">Total Armada</div>
        <div class="text-2xl font-bold font-mono text-noc-text mt-1">{{ serverStore.counts.total }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Node terpantau</div>
      </div>

      <!-- Online Servers -->
      <div class="noc-card p-3 flex flex-col justify-between border-l-2 border-l-emerald-400">
        <div class="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          Aktif Normal
        </div>
        <div class="text-2xl font-bold font-mono text-emerald-400 mt-1">{{ serverStore.counts.up }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Responsif & sehat</div>
      </div>

      <!-- Active Incidents -->
      <div class="noc-card p-3 flex flex-col justify-between border-l-2 border-l-rose-500">
        <div class="text-[11px] font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-rose-500" :class="{ 'animate-ping': problemStore.summary.total_active > 0 }"></span>
          Insiden Aktif
        </div>
        <div class="text-2xl font-bold font-mono text-rose-400 mt-1">{{ problemStore.summary.total_active }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Perlu perhatian operator</div>
      </div>

      <!-- Stale Servers -->
      <div class="noc-card p-3 flex flex-col justify-between border-l-2 border-l-amber-400">
        <div class="text-[11px] font-semibold text-amber-400 uppercase tracking-wider">Terlambat (Stale)</div>
        <div class="text-2xl font-bold font-mono text-amber-400 mt-1">{{ serverStore.counts.stale }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Laporan > 15 detik</div>
      </div>

      <!-- Down Servers -->
      <div class="noc-card p-3 flex flex-col justify-between border-l-2 border-l-slate-500">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Mati (Offline)</div>
        <div class="text-2xl font-bold font-mono text-slate-400 mt-1">{{ serverStore.counts.down }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Tidak terhubung</div>
      </div>

      <!-- Maintenance -->
      <div class="noc-card p-3 flex flex-col justify-between border-l-2 border-l-purple-400">
        <div class="text-[11px] font-semibold text-purple-400 uppercase tracking-wider">Pemeliharaan</div>
        <div class="text-2xl font-bold font-mono text-purple-400 mt-1">{{ serverStore.counts.maintenance }}</div>
        <div class="text-[10px] text-noc-muted mt-0.5">Alarm diredam</div>
      </div>
    </div>

    <!-- Active Problems Strip -->
    <div v-if="problemStore.problems.length > 0" class="noc-card p-3 border-rose-500/30 bg-rose-500/[0.03]">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <span class="text-sm">🚨</span>
          <h2 class="text-xs font-bold uppercase tracking-wider text-rose-400">
            Daftar Masalah & Insiden Terkini (Zabbix-Grade Alerting)
          </h2>
          <span class="noc-badge noc-badge-red">{{ problemStore.problems.length }} masalah</span>
        </div>
        <div class="flex items-center gap-2 text-[11px] text-noc-dim">
          <span>Kritis: <strong class="text-rose-400 font-mono">{{ problemStore.summary.danger }}</strong></span>
          <span>·</span>
          <span>Peringatan: <strong class="text-amber-400 font-mono">{{ problemStore.summary.warning }}</strong></span>
          <span>·</span>
          <span>Diabaikan: <strong class="text-noc-muted font-mono">{{ problemStore.summary.ignored }}</strong></span>
        </div>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th class="w-20">Keparahan</th>
              <th class="w-48">Node Server</th>
              <th>Deskripsi Kendala</th>
              <th class="w-32">Waktu Muncul</th>
              <th class="w-40 text-right">Tindakan Cepat</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="prob in problemStore.problems.slice(0, 8)" :key="prob.id">
              <td>
                <span
                  class="noc-badge uppercase font-bold"
                  :class="{
                    'noc-badge-red': prob.severity === 'danger',
                    'noc-badge-amber': prob.severity === 'warning',
                    'noc-badge-cyan': prob.severity === 'average',
                    'noc-badge-gray': prob.severity === 'info',
                  }"
                >
                  {{ prob.severity }}
                </span>
              </td>
              <td class="font-mono text-xs">
                <router-link :to="`/servers/${prob.server_id}`" class="text-noc-cyan hover:underline font-semibold">
                  {{ prob.hostname || `Server #${prob.server_id}` }}
                </router-link>
              </td>
              <td class="text-noc-text text-xs">
                <div class="font-medium">{{ prob.message }}</div>
                <div v-if="prob.tip" class="text-[10px] text-noc-dim mt-0.5">{{ prob.tip }}</div>
              </td>
              <td class="font-mono text-[11px] text-noc-muted whitespace-nowrap">
                {{ prob.started_at_str || 'Baru saja' }}
              </td>
              <td class="text-right whitespace-nowrap space-x-1">
                <button
                  @click="problemStore.acknowledge(prob.id)"
                  class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]"
                  title="Tandai telah direspons oleh operator"
                >
                  Ack
                </button>
                <button
                  @click="problemStore.resolve(prob.id)"
                  class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-emerald-400"
                  title="Tutup dan selesaikan masalah"
                >
                  Tutup
                </button>
                <button
                  @click="problemStore.ignore(prob.id)"
                  class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-noc-muted"
                  title="Abaikan selama 60 menit"
                >
                  Abaikan
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Filter & Search Toolbar -->
    <div class="flex flex-col sm:flex-row items-center justify-between gap-3 bg-noc-card border border-noc-border p-2.5 rounded-lg text-xs">
      <div class="flex items-center gap-1 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
        <button
          v-for="filter in [
            { id: 'all', label: 'Semua Node' },
            { id: 'up', label: 'Aktif Normal' },
            { id: 'stale', label: 'Terlambat' },
            { id: 'down', label: 'Mati' },
            { id: 'maintenance', label: 'Pemeliharaan' },
          ]"
          :key="filter.id"
          @click="serverStore.filterStatus = filter.id"
          class="px-2.5 py-1 rounded transition-colors whitespace-nowrap font-medium"
          :class="serverStore.filterStatus === filter.id ? 'bg-noc-cyan text-slate-900 font-semibold' : 'text-noc-dim hover:text-noc-text hover:bg-white/[0.04]'"
        >
          {{ filter.label }}
        </button>
      </div>

      <div class="flex items-center gap-2 w-full sm:w-auto">
        <input
          v-model="serverStore.searchQuery"
          type="text"
          placeholder="Cari server (nama, IP)..."
          class="w-full sm:w-64 px-3 py-1 bg-noc-bg border border-noc-border rounded text-xs text-noc-text placeholder-noc-muted focus:outline-none focus:border-noc-cyan"
        />
        <div class="flex items-center gap-1 border border-noc-border rounded p-0.5 bg-noc-bg">
          <button
            @click="viewMode = 'grid'"
            class="px-2 py-0.5 rounded text-[11px]"
            :class="viewMode === 'grid' ? 'bg-white/[0.1] text-noc-text font-semibold' : 'text-noc-muted'"
          >
            Grid
          </button>
          <button
            @click="viewMode = 'table'"
            class="px-2 py-0.5 rounded text-[11px]"
            :class="viewMode === 'table' ? 'bg-white/[0.1] text-noc-text font-semibold' : 'text-noc-muted'"
          >
            Tabel
          </button>
        </div>
      </div>
    </div>

    <!-- Servers View: Grid Mode -->
    <div v-if="viewMode === 'grid'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      <div
        v-for="srv in serverStore.filteredServers"
        :key="srv.id"
        class="noc-card p-3.5 hover:border-noc-border-focus transition-all flex flex-col justify-between group"
      >
        <div>
          <!-- Header: Hostname & Status -->
          <div class="flex items-start justify-between gap-2">
            <div>
              <router-link :to="`/servers/${srv.id}`" class="font-bold text-sm text-noc-text group-hover:text-noc-cyan transition-colors flex items-center gap-1.5">
                <span>{{ srv.hostname }}</span>
              </router-link>
              <div class="font-mono text-[11px] text-noc-muted mt-0.5 flex items-center gap-2">
                <span>{{ srv.ip_address || '—' }}</span>
                <span v-if="srv.os_label" class="truncate max-w-[120px]" :title="srv.os_label">· {{ srv.os_label }}</span>
              </div>
            </div>

            <!-- Status Pill -->
            <span
              class="noc-badge uppercase font-bold"
              :class="{
                'noc-badge-green': srv.status === 'up' && !srv.is_maintenance,
                'noc-badge-red': srv.status === 'down',
                'noc-badge-amber': srv.status === 'stale',
                'noc-badge-purple': srv.is_maintenance,
              }"
            >
              {{ srv.is_maintenance ? 'MAINT' : srv.status.toUpperCase() }}
            </span>
          </div>

          <!-- Gauges: CPU, RAM, Disk -->
          <div class="mt-3.5 space-y-2 text-xs">
            <!-- CPU -->
            <div>
              <div class="flex justify-between text-[11px] mb-0.5">
                <span class="text-noc-dim">CPU</span>
                <span class="font-mono text-noc-text">{{ srv.cpu_pct !== undefined && srv.cpu_pct !== null ? `${Math.round(srv.cpu_pct)}%` : '—' }}</span>
              </div>
              <div class="w-full h-1.5 bg-noc-surface rounded-full overflow-hidden">
                <div
                  class="h-full transition-all duration-500 rounded-full"
                  :class="srv.cpu_pct > 90 ? 'bg-rose-500' : srv.cpu_pct > 75 ? 'bg-amber-400' : 'bg-noc-cyan'"
                  :style="{ width: `${Math.min(srv.cpu_pct || 0, 100)}%` }"
                ></div>
              </div>
            </div>

            <!-- RAM -->
            <div>
              <div class="flex justify-between text-[11px] mb-0.5">
                <span class="text-noc-dim">Memori</span>
                <span class="font-mono text-noc-text">{{ srv.ram_pct !== undefined && srv.ram_pct !== null ? `${Math.round(srv.ram_pct)}%` : '—' }}</span>
              </div>
              <div class="w-full h-1.5 bg-noc-surface rounded-full overflow-hidden">
                <div
                  class="h-full transition-all duration-500 rounded-full"
                  :class="srv.ram_pct > 90 ? 'bg-rose-500' : srv.ram_pct > 80 ? 'bg-amber-400' : 'bg-emerald-400'"
                  :style="{ width: `${Math.min(srv.ram_pct || 0, 100)}%` }"
                ></div>
              </div>
            </div>

            <!-- Disk -->
            <div>
              <div class="flex justify-between text-[11px] mb-0.5">
                <span class="text-noc-dim">Penyimpanan Root</span>
                <span class="font-mono text-noc-text">{{ srv.disk_pct !== undefined && srv.disk_pct !== null ? `${Math.round(srv.disk_pct)}%` : '—' }}</span>
              </div>
              <div class="w-full h-1.5 bg-noc-surface rounded-full overflow-hidden">
                <div
                  class="h-full transition-all duration-500 rounded-full"
                  :class="srv.disk_pct > 90 ? 'bg-rose-500' : srv.disk_pct > 80 ? 'bg-amber-400' : 'bg-purple-400'"
                  :style="{ width: `${Math.min(srv.disk_pct || 0, 100)}%` }"
                ></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer / Quick Action Bar -->
        <div class="mt-4 pt-2.5 border-t border-noc-border/40 flex items-center justify-between text-[11px] text-noc-muted">
          <div class="flex items-center gap-1.5">
            <span class="font-mono">v{{ srv.agent_version || '—' }}</span>
            <span v-if="srv.agent_outdated" class="text-amber-400 text-[10px]" title="Versi agen usang">↑ update</span>
          </div>

          <div class="flex items-center gap-1">
            <router-link :to="`/servers/${srv.id}`" class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]">
              Buka Rincian →
            </router-link>
          </div>
        </div>
      </div>
    </div>

    <!-- Servers View: High Density Table Mode -->
    <div v-else class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-12 text-center">Status</th>
            <th>Nama Host</th>
            <th>Alamat IP</th>
            <th>OS & Kernel</th>
            <th class="w-24">CPU</th>
            <th class="w-24">Memori</th>
            <th class="w-24">Disk</th>
            <th class="w-24">Uptime</th>
            <th class="w-20">Agen</th>
            <th class="w-28 text-right">Aksi</th>
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
            <td class="text-xs text-noc-muted truncate max-w-[180px]">{{ srv.os_label || 'Linux' }}</td>
            <td class="font-mono text-xs">
              <span :class="srv.cpu_pct > 90 ? 'text-rose-400 font-bold' : 'text-noc-text'">
                {{ srv.cpu_pct !== undefined && srv.cpu_pct !== null ? `${Math.round(srv.cpu_pct)}%` : '—' }}
              </span>
            </td>
            <td class="font-mono text-xs">
              <span :class="srv.ram_pct > 90 ? 'text-rose-400 font-bold' : 'text-noc-text'">
                {{ srv.ram_pct !== undefined && srv.ram_pct !== null ? `${Math.round(srv.ram_pct)}%` : '—' }}
              </span>
            </td>
            <td class="font-mono text-xs">
              <span :class="srv.disk_pct > 90 ? 'text-rose-400 font-bold' : 'text-noc-text'">
                {{ srv.disk_pct !== undefined && srv.disk_pct !== null ? `${Math.round(srv.disk_pct)}%` : '—' }}
              </span>
            </td>
            <td class="font-mono text-xs text-noc-muted">{{ srv.uptime_str || '—' }}</td>
            <td class="font-mono text-xs text-noc-muted">v{{ srv.agent_version || '—' }}</td>
            <td class="text-right">
              <router-link :to="`/servers/${srv.id}`" class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px]">
                Buka
              </router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useServerStore } from '@/stores/servers'
import { useProblemStore } from '@/stores/problems'

const serverStore = useServerStore()
const problemStore = useProblemStore()
const viewMode = ref('grid')

onMounted(() => {
  serverStore.startPolling(5000)
  problemStore.startPolling(6000)
})

onUnmounted(() => {
  serverStore.stopPolling()
  problemStore.stopPolling()
})
</script>
