<template>
  <div class="space-y-4">
    <!-- Hardware Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
      <!-- CPU Specs -->
      <div class="noc-card p-3">
        <h4 class="text-[11px] font-bold text-noc-dim uppercase mb-2">Prosesor (CPU)</h4>
        <div class="font-bold text-sm text-noc-text truncate" :title="specs?.cpu?.model || '—'">
          {{ specs?.cpu?.model || 'Intel / AMD Processor' }}
        </div>
        <div class="mt-2 space-y-1 text-xs font-mono text-noc-muted">
          <div class="flex justify-between">
            <span class="text-noc-dim">Arsitektur:</span>
            <span class="text-noc-text">{{ specs?.cpu?.arch || overview?.arch || 'x86_64' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Core Fisik / Thread:</span>
            <span class="text-noc-text">{{ specs?.cpu?.cores || '—' }} Core / {{ specs?.cpu?.threads || '—' }} Thread</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Virtualisasi:</span>
            <span class="text-noc-cyan">{{ specs?.platform?.type || 'KVM / Baremetal' }}</span>
          </div>
        </div>
      </div>

      <!-- Memory Specs -->
      <div class="noc-card p-3">
        <h4 class="text-[11px] font-bold text-noc-dim uppercase mb-2">Memori RAM Fisik</h4>
        <div class="font-bold text-sm text-noc-text font-mono">
          {{ formatBytes(overview?.mem_total) }}
        </div>
        <div class="mt-2 space-y-1 text-xs font-mono text-noc-muted">
          <div class="flex justify-between">
            <span class="text-noc-dim">Tipe Modul:</span>
            <span class="text-noc-text">{{ specs?.memory?.type || 'DDR4 / ECC' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Slot Terpasang:</span>
            <span class="text-noc-text">{{ specs?.memory?.slots || 'Terintegrasi' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Swap Terkonfigurasi:</span>
            <span class="text-noc-text">{{ formatBytes(overview?.swap_total) }}</span>
          </div>
        </div>
      </div>

      <!-- Motherboard / System Specs -->
      <div class="noc-card p-3">
        <h4 class="text-[11px] font-bold text-noc-dim uppercase mb-2">Papan Induk & BIOS</h4>
        <div class="font-bold text-sm text-noc-text truncate">
          {{ specs?.system?.vendor || 'Standard Host' }}
        </div>
        <div class="mt-2 space-y-1 text-xs font-mono text-noc-muted">
          <div class="flex justify-between">
            <span class="text-noc-dim">Model:</span>
            <span class="text-noc-text truncate max-w-[140px]">{{ specs?.system?.product || 'System Board' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Versi BIOS:</span>
            <span class="text-noc-text">{{ specs?.system?.bios_version || '—' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-noc-dim">Waktu Boot:</span>
            <span class="text-noc-text">{{ overview?.uptime_str || '—' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- S.M.A.R.T. Disk Health Diagnostics Table -->
    <div class="noc-card p-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>🩺</span>
        <span>Diagnostik Kesehatan Disk S.M.A.R.T.</span>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Perangkat</th>
              <th>Model / Serial</th>
              <th>Kapasitas</th>
              <th>Status Kesehatan</th>
              <th>Suhu (°C)</th>
              <th>Reallocated Sectors</th>
              <th>Tingkat Keausan (Wear)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in smartDisks" :key="d.device">
              <td class="font-mono font-bold text-noc-cyan">{{ d.device }}</td>
              <td class="font-mono text-xs text-noc-text">{{ d.model || 'Generic Storage' }}</td>
              <td class="font-mono text-xs">{{ formatBytes(d.size_bytes) }}</td>
              <td>
                <span
                  class="noc-badge uppercase font-bold"
                  :class="d.health === 'PASSED' ? 'noc-badge-green' : 'noc-badge-red'"
                >
                  {{ d.health || 'PASSED' }}
                </span>
              </td>
              <td class="font-mono text-xs">{{ d.temp_c ? `${d.temp_c} °C` : '—' }}</td>
              <td class="font-mono text-xs">{{ d.reallocated_sectors !== undefined ? d.reallocated_sectors : '0' }}</td>
              <td class="font-mono text-xs">{{ d.wear_level !== undefined ? `${d.wear_level}%` : '—' }}</td>
            </tr>
            <tr v-if="smartDisks.length === 0">
              <td colspan="7" class="text-center py-4 text-noc-muted">Tidak ada data diagnostik S.M.A.R.T. langsung (disk virtual / NVMe dasar)</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: Object,
})

const specs = computed(() => {
  return props.overview?.hardware_specs || {}
})

const smartDisks = computed(() => {
  return specs.value?.disks || []
})

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}
</script>
