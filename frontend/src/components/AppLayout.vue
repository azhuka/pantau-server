<template>
  <div class="layout-root">
    <!-- SIDEBAR NAVIGASI NOC ORISINAL -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="brand-dot">
          <circle cx="12" cy="12" r="10"></circle>
          <circle cx="12" cy="12" r="2" fill="currentColor"></circle>
        </svg>
        <span>Pantau Server</span>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-section">Menu</div>
        <router-link to="/" class="nav-link" exact-active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          </span>
          <span>Dashboard</span>
        </router-link>

        <router-link to="/servers" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
          </span>
          <span>Daftar Server</span>
        </router-link>

        <router-link to="/problems" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          </span>
          <span>Insiden</span>
          <span v-if="alertCount > 0" class="badge badge-danger" style="margin-left:auto;font-size:8px;padding:0 5px">{{ alertCount }}</span>
        </router-link>

        <router-link to="/probing" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2"></circle><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"></path></svg>
          </span>
          <span>Pantau Endpoint</span>
        </router-link>

        <router-link to="/logs" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
          </span>
          <span>Log</span>
        </router-link>

        <div class="nav-section" style="margin-top:14px">Kelola</div>
        <router-link to="/maintenance" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
          </span>
          <span>Pemeliharaan</span>
        </router-link>

        <router-link to="/audit" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          </span>
          <span>Riwayat Tindakan</span>
        </router-link>

        <router-link to="/profile" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          </span>
          <span>Akun Pengguna</span>
        </router-link>

        <router-link to="/master-control" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
          </span>
          <span>Master Control</span>
        </router-link>

        <router-link to="/settings" class="nav-link" active-class="active">
          <span class="nav-icon">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path><path d="M2 12h20"></path></svg>
          </span>
          <span>Kustomisasi UI</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div style="font-size:11px;color:var(--dim)">v4.8.125 &middot; UTC {{ utcClock }}</div>
        <div style="font-weight:700;font-size:13px;color:var(--text);margin-top:4px" class="mono">{{ currentUser.username || 'master-admin' }}</div>
        <div style="margin-top:3px">
          <span class="badge badge-danger" style="font-size:8px;padding:0.5px 4.5px">{{ currentUser.role_display || 'MASTER ADMIN' }}</span>
        </div>
        <div style="margin-top:8px">
          <a href="/logout" @click.prevent="logout" style="color:var(--dim);font-size:11px;text-decoration:none">Keluar</a>
        </div>
      </div>
    </aside>

    <!-- AREA KONTEN UTAMA -->
    <main class="main-content">
      <!-- HEADER BRANDING DINAS KOMINFO BARRU (NOC HEADER) -->
      <div class="dash-org-header" style="text-align:center;margin:8px auto 20px auto;padding-top:4px;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%">
        <div class="dash-brand-wrap" style="position:relative;display:inline-flex;flex-direction:column;justify-content:center;gap:4px;text-align:center;min-height:68px;height:auto;max-width:calc(100% - 240px);padding:4px 0">
          <div class="dash-brand-logo-box" style="position:absolute;right:calc(100% + 18px);top:50%;transform:translateY(-50%);display:flex;align-items:center;justify-content:flex-end;flex-shrink:0">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="color:var(--blue);filter:drop-shadow(0 0 10px rgba(56,189,248,0.4))">
              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
              <path d="M2 17l10 5 10-5"></path>
              <path d="M2 12l10 5 10-5"></path>
            </svg>
          </div>
          <div class="dash-brand-title" style="font-size:20px;font-weight:800;letter-spacing:1.5px;color:var(--text-heading, #fff);text-transform:uppercase;line-height:1;margin:0">PANTAU SERVER</div>
          <div style="font-size:14.5px;font-weight:700;color:var(--text-bright, #fff);letter-spacing:0.2px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%">DINAS KOMUNIKASI INFORMATIKA STATISTIK DAN PERSANDIAN KAB. BARRU</div>
          <div style="font-size:12.5px;color:var(--dim);font-style:italic;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;padding-bottom:1px">Bidang Aplikasi dan Informatika</div>
        </div>
      </div>

      <!-- ROUTER VIEW RENDERING KONTEN HALAMAN SECARA INSTAN TANPA KEDIP -->
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { api } from '@/api';

const alertCount = ref(0);
const utcClock = ref('00:00:00');
const currentUser = ref({ username: 'master-admin', role_display: 'MASTER ADMIN' });
let clockTimer = null;
let pollTimer = null;

function updateClock() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  utcClock.value = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

async function fetchStatus() {
  try {
    const data = await api.get('/api/alerts');
    alertCount.value = (data.firing_danger_count || 0) + (data.firing_average_count || 0) + (data.firing_warning_count || 0);
  } catch (e) {
    // abaikan jika belum login
  }
}

async function fetchCurrentUser() {
  try {
    const user = await api.get('/api/auth/me');
    if (user && user.username) currentUser.value = user;
  } catch (e) {
    // fallback
  }
}

async function logout() {
  try {
    await api.post('/api/auth/logout', {});
  } finally {
    window.location.href = '/login';
  }
}

onMounted(() => {
  updateClock();
  clockTimer = setInterval(updateClock, 1000);
  fetchCurrentUser();
  fetchStatus();
  pollTimer = setInterval(fetchStatus, 10000);
});

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
.layout-root {
  display: flex;
  min-height: 100vh;
  width: 100%;
}
</style>
