<template>
  <div class="space-y-4">
    <!-- Scheduled Jobs Table -->
    <div class="noc-card p-3">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim flex items-center gap-2">
          <span>⏰</span>
          <span>Tugas Terjadwal Cron (/etc/crontab & user crontabs)</span>
        </h3>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th class="w-28">Jadwal Cron</th>
              <th>Pengguna</th>
              <th>Perintah Shell yang Dijalankan</th>
              <th>Sumber Berkas</th>
              <th class="w-20 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in cronJobs" :key="`${job.source}-${job.line}`">
              <td class="font-mono text-xs font-bold text-noc-cyan">{{ job.schedule }}</td>
              <td class="font-bold text-xs text-noc-text">{{ job.user }}</td>
              <td class="font-mono text-xs text-noc-dim truncate max-w-md">{{ job.command }}</td>
              <td class="font-mono text-[11px] text-noc-muted">{{ job.source }}</td>
              <td class="text-center">
                <span class="noc-badge" :class="job.is_enabled ? 'noc-badge-green' : 'noc-badge-gray'">
                  {{ job.is_enabled ? 'AKTIF' : 'NONAKTIF' }}
                </span>
              </td>
            </tr>
            <tr v-if="cronJobs.length === 0">
              <td colspan="5" class="text-center py-4 text-noc-muted">Tidak ada cron job terjadwal yang terdeteksi</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Systemd Timers -->
    <div class="noc-card p-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>⏱️</span>
        <span>Systemd Timers Terjadwal</span>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Nama Timer</th>
              <th>Memicu Layanan (Activates)</th>
              <th>Jadwal Pemicu</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in timers" :key="t.timer">
              <td class="font-mono text-xs font-bold text-noc-cyan">{{ t.timer }}</td>
              <td class="font-mono text-xs text-noc-text">{{ t.activates }}</td>
              <td class="font-mono text-[11px] text-noc-muted">{{ t.raw || '—' }}</td>
            </tr>
            <tr v-if="timers.length === 0">
              <td colspan="3" class="text-center py-4 text-noc-muted">Tidak ada systemd timer aktif</td>
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

const cronJobs = computed(() => {
  return props.overview?.cron_jobs?.jobs || []
})

const timers = computed(() => {
  return props.overview?.cron_jobs?.timers || []
})
</script>
