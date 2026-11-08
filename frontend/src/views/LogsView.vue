<template>
  <div>
    <div class="topbar">
      <h2>Log Server Pantau-Server</h2>
      <div class="mono" style="font-size:12px;color:var(--dim)">Host: <strong>{{ sys.hostname || 'rj45' }}</strong> &middot; Uptime: {{ sys.uptime_str || '-' }}</div>
    </div>

    <!-- METRIK LIVE PUSAT -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="label">CPU</div>
        <div class="value mono">{{ sys.cpu_percent != null ? sys.cpu_percent.toFixed(1) : '-' }}%</div>
      </div>
      <div class="stat-card">
        <div class="label">Memori</div>
        <div class="value mono">{{ sys.mem_percent != null ? sys.mem_percent.toFixed(1) : '-' }}%</div>
      </div>
      <div class="stat-card">
        <div class="label">Beban Sistem</div>
        <div class="value mono" style="font-size:16px">{{ sys.loadavg || '-' }}</div>
      </div>
    </div>

    <!-- TERMINAL LOG VIEWER -->
    <div class="card">
      <div class="card-header">
        <h3>Log Layanan Aplikasi</h3>
        <span class="badge badge-up">Live Streaming</span>
      </div>
      <pre style="background:var(--input-bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:11.5px;font-family:monospace;line-height:1.55;height:50vh;overflow:auto;color:var(--text);white-space:pre-wrap">{{ logContent }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { api } from '@/api';

const sys = ref({});
const logContent = ref('Memuat log sistem...');
let pollTimer = null;

async function fetchSys() {
  try {
    const data = await api.get('/api/system/status');
    if (data) sys.value = data;
  } catch (e) {
    try {
      const data2 = await api.get('/api/system/overview');
      if (data2) sys.value = data2;
    } catch (e2) {}
  }

  try {
    const logs = await api.get('/api/logs/dashboard?lines=100');
    if (logs && logs.lines) {
      logContent.value = logs.lines.join('\n');
    } else if (typeof logs === 'string') {
      logContent.value = logs;
    }
  } catch (e) {
    try {
      const logs2 = await api.get('/api/system/logs?lines=100');
      if (logs2 && logs2.lines) logContent.value = logs2.lines.join('\n');
    } catch (e2) {}
  }
}

onMounted(() => {
  fetchSys();
  pollTimer = setInterval(fetchSys, 3000);
});

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>
