<template>
  <div>
    <!-- KPI STRIP RINGKASAN -->
    <div class="stats-grid">
      <div class="stat-card" style="border-left: 3px solid var(--blue)">
        <div class="label">Total Server</div>
        <div class="value">{{ totalServers }} <span style="font-size:13px;color:var(--dim);font-weight:600">host</span></div>
        <div style="margin-top:6px;display:flex;gap:6px">
          <span class="badge badge-up">{{ upServers }} UP</span>
          <span class="badge badge-down">{{ downServers }} DOWN</span>
        </div>
      </div>

      <div class="stat-card" style="border-left: 3px solid var(--red)">
        <div class="label">Insiden Aktif</div>
        <div class="value" :style="{ color: dangerCount > 0 ? 'var(--red)' : 'var(--text-heading)' }">
          {{ totalProblems }}
        </div>
        <div style="margin-top:6px;display:flex;gap:4px">
          <span v-if="dangerCount" class="badge badge-danger">{{ dangerCount }} Kritis</span>
          <span v-if="warnCount" class="badge badge-warn">{{ warnCount }} Peringatan</span>
          <span v-if="!totalProblems" class="badge badge-up">Semua Normal</span>
        </div>
      </div>

      <div class="stat-card" style="border-left: 3px solid var(--green)">
        <div class="label">Waktu Sistem (WITA)</div>
        <div class="value mono" style="font-size:20px">{{ localClock }}</div>
        <div style="font-size:11px;color:var(--dim);margin-top:6px">{{ localDate }}</div>
      </div>
    </div>

    <!-- KARTU INSIDEN TERKINI -->
    <div class="card" v-if="problems.length > 0">
      <div class="card-header">
        <div style="display:flex;align-items:center;gap:8px">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--yellow)"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          <h3>Insiden Terkini</h3>
          <span class="badge badge-warn">{{ problems.length }} Insiden</span>
        </div>
        <router-link to="/problems" class="btn btn-ghost btn-sm">Lihat Semua Insiden &rarr;</router-link>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:115px">Waktu</th>
              <th style="width:160px">Server</th>
              <th style="width:110px;text-align:center">Keparahan</th>
              <th style="min-width:240px">Deskripsi Insiden</th>
              <th style="width:110px;text-align:right">Durasi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in problems" :key="p.id">
              <td class="mono" style="font-size:10px">{{ p.started_at_str || '-' }}</td>
              <td><strong>{{ p.hostname }}</strong></td>
              <td style="text-align:center">
                <span :class="['badge', `badge-${p.severity === 'danger' ? 'danger' : (p.severity === 'average' ? 'warn' : 'info')}`]">
                  {{ p.severity.toUpperCase() }}
                </span>
              </td>
              <td>{{ p.message }}</td>
              <td class="mono" style="text-align:right;font-size:10px">{{ p.durasi || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- KARTU STATUS & KINERJA SERVER -->
    <div class="card">
      <div class="card-header">
        <div>
          <h3>Status &amp; Kinerja Armada Server</h3>
          <div style="font-size:11.5px;color:var(--dim);margin-top:2px">Kondisi kesehatan telemetri host secara real-time.</div>
        </div>
        <div style="display:flex;gap:8px">
          <input type="text" v-model="searchQ" class="filter-input" placeholder="Cari host atau IP..." style="width:180px;height:30px">
          <button class="btn btn-ghost btn-sm" @click="fetchData">Segarkan</button>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sticky-left" style="width:180px">Server</th>
              <th style="width:85px;text-align:center">Status</th>
              <th style="width:140px">Platform / IP</th>
              <th style="width:85px">Uptime</th>
              <th style="width:120px">CPU</th>
              <th style="width:140px">RAM</th>
              <th style="width:140px">Storage</th>
              <th class="col-act" style="width:80px">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredServers" :key="s.id">
              <td class="sticky-left">
                <div style="display:flex;align-items:center;gap:6px">
                  <span :class="['dot', s.is_online ? 'up' : 'down']"></span>
                  <strong style="color:var(--text-heading)">{{ s.hostname }}</strong>
                </div>
              </td>
              <td style="text-align:center">
                <span :class="['badge', s.is_online ? 'badge-up' : 'badge-down']">
                  {{ s.is_online ? 'ONLINE' : 'OFFLINE' }}
                </span>
              </td>
              <td class="mono" style="font-size:10.5px">
                <div>{{ s.platform || 'Linux' }}</div>
                <div style="color:var(--dim)">{{ s.ip_address }}</div>
              </td>
              <td class="mono" style="font-size:10.5px">{{ s.uptime_str || '-' }}</td>
              <td>
                <div style="font-size:10.5px;font-weight:700" class="mono">{{ (s.cpu_percent || 0).toFixed(1) }}%</div>
                <div style="height:3px;background:rgba(255,255,255,0.1);border-radius:2px;overflow:hidden;margin-top:2px">
                  <div style="height:100%;background:var(--blue)" :style="{ width: `${Math.min(100, s.cpu_percent || 0)}%` }"></div>
                </div>
              </td>
              <td>
                <div style="font-size:10.5px;font-weight:700" class="mono">{{ (s.mem_percent || 0).toFixed(1) }}%</div>
                <div style="font-size:9.5px;color:var(--dim)">{{ s.mem_used_str || '-' }} / {{ s.mem_total_str || '-' }}</div>
              </td>
              <td>
                <div style="font-size:10.5px;font-weight:700" class="mono">{{ (s.disk_percent || 0).toFixed(1) }}%</div>
                <div style="font-size:9.5px;color:var(--dim)">Sisa {{ s.disk_free_str || '-' }}</div>
              </td>
              <td class="col-act">
                <router-link :to="`/servers?focus=${s.id}`" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px">Rincian</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { api } from '@/api';

const servers = ref([]);
const problems = ref([]);
const searchQ = ref('');
const localClock = ref('');
const localDate = ref('');
let timer = null;

const totalServers = computed(() => servers.value.length);
const upServers = computed(() => servers.value.filter(s => s.is_online).length);
const downServers = computed(() => servers.value.filter(s => !s.is_online).length);

const totalProblems = computed(() => problems.value.length);
const dangerCount = computed(() => problems.value.filter(p => p.severity === 'danger').length);
const warnCount = computed(() => problems.value.filter(p => p.severity === 'warning' || p.severity === 'average').length);

const filteredServers = computed(() => {
  if (!searchQ.value) return servers.value;
  const q = searchQ.value.toLowerCase();
  return servers.value.filter(s =>
    (s.hostname && s.hostname.toLowerCase().includes(q)) ||
    (s.ip_address && s.ip_address.includes(q))
  );
});

function updateTime() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  localClock.value = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const days = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
  const months = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
  localDate.value = `${days[d.getDay()]}, ${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

async function fetchData() {
  try {
    const data = await api.get('/api/servers');
    if (data && data.servers) {
      servers.value = data.servers;
    } else if (Array.isArray(data)) {
      servers.value = data;
    }
  } catch (e) {
    // fallback
  }

  try {
    const probData = await api.get('/api/problems');
    if (probData && probData.open_problems) {
      problems.value = probData.open_problems;
    } else if (probData && probData.problems) {
      problems.value = probData.problems;
    } else if (Array.isArray(probData)) {
      problems.value = probData;
    }
  } catch (e) {
    // fallback
  }
}

onMounted(() => {
  updateTime();
  fetchData();
  timer = setInterval(() => {
    updateTime();
    fetchData();
  }, 5000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>
