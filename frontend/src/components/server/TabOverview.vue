<template>
  <div class="space-y-4">
    <!-- Top KPI Gauges -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <!-- CPU Gauge -->
      <div class="noc-card p-3">
        <div class="flex items-center justify-between text-[11px] font-semibold text-noc-dim uppercase">
          <span>Penggunaan CPU</span>
          <span class="font-mono text-noc-text text-sm font-bold">{{ Math.round(overview?.cpu || 0) }}%</span>
        </div>
        <div class="w-full h-2 bg-noc-surface rounded-full overflow-hidden mt-2">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="(overview?.cpu || 0) > 90 ? 'bg-rose-500' : (overview?.cpu || 0) > 75 ? 'bg-amber-400' : 'bg-noc-cyan'"
            :style="{ width: `${Math.min(overview?.cpu || 0, 100)}%` }"
          ></div>
        </div>
        <div class="flex justify-between items-center text-[10px] text-noc-muted mt-2 font-mono">
          <span>Load 1m: {{ overview?.load1 || '0.00' }}</span>
          <span>5m: {{ overview?.load5 || '0.00' }}</span>
          <span>15m: {{ overview?.load15 || '0.00' }}</span>
        </div>
      </div>

      <!-- RAM Gauge -->
      <div class="noc-card p-3">
        <div class="flex items-center justify-between text-[11px] font-semibold text-noc-dim uppercase">
          <span>Penggunaan RAM</span>
          <span class="font-mono text-noc-text text-sm font-bold">{{ Math.round(ramPct) }}%</span>
        </div>
        <div class="w-full h-2 bg-noc-surface rounded-full overflow-hidden mt-2">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="ramPct > 90 ? 'bg-rose-500' : ramPct > 80 ? 'bg-amber-400' : 'bg-emerald-400'"
            :style="{ width: `${Math.min(ramPct, 100)}%` }"
          ></div>
        </div>
        <div class="flex justify-between items-center text-[10px] text-noc-muted mt-2 font-mono">
          <span>Terpakai: {{ formatBytes(overview?.mem_used) }}</span>
          <span>Total: {{ formatBytes(overview?.mem_total) }}</span>
        </div>
      </div>

      <!-- Swap Gauge -->
      <div class="noc-card p-3">
        <div class="flex items-center justify-between text-[11px] font-semibold text-noc-dim uppercase">
          <span>Penggunaan Swap</span>
          <span class="font-mono text-noc-text text-sm font-bold">{{ Math.round(swapPct) }}%</span>
        </div>
        <div class="w-full h-2 bg-noc-surface rounded-full overflow-hidden mt-2">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="swapPct > 80 ? 'bg-rose-500' : 'bg-purple-400'"
            :style="{ width: `${Math.min(swapPct, 100)}%` }"
          ></div>
        </div>
        <div class="flex justify-between items-center text-[10px] text-noc-muted mt-2 font-mono">
          <span>Terpakai: {{ formatBytes(overview?.swap_used) }}</span>
          <span>Total: {{ formatBytes(overview?.swap_total) }}</span>
        </div>
      </div>

      <!-- Root Storage Runway Gauge -->
      <div class="noc-card p-3">
        <div class="flex items-center justify-between text-[11px] font-semibold text-noc-dim uppercase">
          <span>Penyimpanan / Root</span>
          <span class="font-mono text-noc-text text-sm font-bold">{{ Math.round(rootDisk?.pct || 0) }}%</span>
        </div>
        <div class="w-full h-2 bg-noc-surface rounded-full overflow-hidden mt-2">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="(rootDisk?.pct || 0) > 90 ? 'bg-rose-500' : (rootDisk?.pct || 0) > 80 ? 'bg-amber-400' : 'bg-sky-400'"
            :style="{ width: `${Math.min(rootDisk?.pct || 0, 100)}%` }"
          ></div>
        </div>
        <div class="flex justify-between items-center text-[10px] text-noc-muted mt-2 font-mono">
          <span>Terpakai: {{ formatBytes(rootDisk?.used) }}</span>
          <span>Kapasitas: {{ formatBytes(rootDisk?.total) }}</span>
        </div>
      </div>
    </div>

    <!-- Storage Devices Table & Top Processes Split -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <!-- Disks Table -->
      <div class="noc-card p-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-1.5">
          <span>💾</span>
          <span>Alokasi Perangkat Penyimpanan</span>
        </h3>
        <div class="overflow-x-auto">
          <table class="w-full noc-table text-left">
            <thead>
              <tr>
                <th>Titik Kait (Mount)</th>
                <th>Tipe</th>
                <th>Kapasitas</th>
                <th>Terpakai</th>
                <th class="w-24">Persentase</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in overview?.disks || []" :key="d.mount">
                <td class="font-mono font-medium text-noc-cyan">{{ d.mount }}</td>
                <td class="text-noc-muted font-mono text-[11px]">{{ d.type }}</td>
                <td class="font-mono">{{ formatBytes(d.total) }}</td>
                <td class="font-mono">{{ formatBytes(d.used) }}</td>
                <td>
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1.5 bg-noc-surface rounded-full overflow-hidden">
                      <div
                        class="h-full rounded-full"
                        :class="d.pct > 90 ? 'bg-rose-500' : d.pct > 80 ? 'bg-amber-400' : 'bg-noc-cyan'"
                        :style="{ width: `${Math.min(d.pct || 0, 100)}%` }"
                      ></div>
                    </div>
                    <span class="font-mono text-[10px] w-8 text-right">{{ Math.round(d.pct || 0) }}%</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Top Processes -->
      <div class="noc-card p-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-1.5">
          <span>⚡</span>
          <span>Proses Konsumsi Tertinggi (Top Processes)</span>
        </h3>
        <div class="overflow-x-auto">
          <table class="w-full noc-table text-left">
            <thead>
              <tr>
                <th class="w-16">PID</th>
                <th>Perintah / Proses</th>
                <th>Pengguna</th>
                <th class="w-16 text-right">CPU</th>
                <th class="w-16 text-right">Memori</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in topProcs" :key="p.pid">
                <td class="font-mono text-[11px] text-noc-muted">{{ p.pid }}</td>
                <td class="font-mono font-medium text-noc-text truncate max-w-[140px]">{{ p.comm }}</td>
                <td class="text-noc-dim text-[11px]">{{ p.user }}</td>
                <td class="font-mono text-right text-noc-cyan font-semibold">{{ p.cpu }}%</td>
                <td class="font-mono text-right text-emerald-400">{{ p.mem }}%</td>
              </tr>
              <tr v-if="topProcs.length === 0">
                <td colspan="5" class="text-center py-4 text-noc-muted">Tidak ada data proses aktif saat ini</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: Object,
})

const ramPct = computed(() => {
  if (!props.overview?.mem_total || props.overview.mem_total === 0) return 0
  return ((props.overview?.mem_used || 0) / props.overview.mem_total) * 100
})

const swapPct = computed(() => {
  if (!props.overview?.swap_total || props.overview.swap_total === 0) return 0
  return ((props.overview?.swap_used || 0) / props.overview.swap_total) * 100
})

const rootDisk = computed(() => {
  const disks = props.overview?.disks || []
  return disks.find((d) => d.mount === '/') || disks[0] || null
})

const topProcs = computed(() => {
  const tp = props.overview?.top_procs
  if (!tp) return []
  return (tp.cpu || []).slice(0, 6)
})

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}
</script>
