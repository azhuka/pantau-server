<template>
  <div class="space-y-4">
    <!-- Server Top Header Banner -->
    <div class="bg-noc-card border border-noc-border p-3.5 rounded-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
      <div>
        <div class="flex items-center gap-2">
          <router-link to="/servers" class="text-noc-muted hover:text-noc-cyan text-xs font-mono">
            ← Armada Server
          </router-link>
          <span class="text-noc-muted">/</span>
          <h1 class="text-base font-bold text-noc-text flex items-center gap-2">
            <span>{{ overview?.server?.hostname || 'Memuat server...' }}</span>
            <span
              class="noc-badge uppercase font-bold text-[10px]"
              :class="{
                'noc-badge-green': overview?.server?.status === 'up' && !overview?.server?.is_maintenance,
                'noc-badge-red': overview?.server?.status === 'down',
                'noc-badge-amber': overview?.server?.status === 'stale',
                'noc-badge-purple': overview?.server?.is_maintenance,
              }"
            >
              {{ overview?.server?.is_maintenance ? 'MAINT' : (overview?.server?.status || 'UNKNOWN').toUpperCase() }}
            </span>
          </h1>
        </div>

        <div class="mt-1 flex flex-wrap items-center gap-3 text-xs font-mono text-noc-muted">
          <span>IP: <strong class="text-noc-text">{{ overview?.server?.ip_address || '—' }}</strong></span>
          <span>·</span>
          <span>OS: <span class="text-noc-dim">{{ overview?.server?.os_label || 'Linux' }}</span></span>
          <span>·</span>
          <span>Uptime: <span class="text-noc-dim">{{ overview?.server?.uptime_str || '—' }}</span></span>
          <span>·</span>
          <span>Agen: <span class="text-noc-dim">v{{ overview?.server?.agent_version || '—' }}</span></span>
        </div>
      </div>

      <!-- Quick Server Actions (Power, OTA, Maintenance) -->
      <div class="flex items-center gap-2 self-stretch sm:self-auto justify-end">
        <button
          v-if="overview?.server?.agent_outdated"
          @click="updateAgent"
          class="noc-btn noc-btn-secondary text-amber-400 border-amber-500/30 text-xs py-1 px-2.5"
          title="Perbarui agen ke versi terbaru"
        >
          ↑ Update Agen
        </button>
        <button
          @click="rebootHost"
          class="noc-btn noc-btn-secondary text-xs py-1 px-2.5"
          title="Reboot sistem host jarak jauh"
        >
          Reboot
        </button>
        <button
          @click="poweroffHost"
          class="noc-btn noc-btn-secondary text-rose-400 border-rose-500/30 text-xs py-1 px-2.5"
          title="Matikan mesin host"
        >
          Power OFF
        </button>
      </div>
    </div>

    <!-- Tab Navigation Bar -->
    <div class="flex items-center gap-1 border-b border-noc-border pb-1 overflow-x-auto text-xs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        class="px-3 py-1.5 rounded-t font-medium transition-colors whitespace-nowrap flex items-center gap-1.5"
        :class="activeTab === tab.id ? 'bg-noc-card border-t-2 border-noc-cyan text-noc-cyan font-semibold border-x border-noc-border' : 'text-noc-dim hover:text-noc-text hover:bg-white/[0.03]'"
      >
        <span>{{ tab.icon }}</span>
        <span>{{ tab.label }}</span>
        <span v-if="tab.badge" class="noc-badge noc-badge-amber text-[9px] py-0 px-1">{{ tab.badge }}</span>
      </button>
    </div>

    <!-- Active Tab Component Rendering -->
    <div>
      <TabOverview v-if="activeTab === 'overview'" :overview="overview" />
      <TabServices v-else-if="activeTab === 'services'" :server-id="serverId" :services="overview?.services || []" @refresh="fetchData" />
      <TabTerminal v-else-if="activeTab === 'terminal'" :server-id="serverId" />
      <TabFiles v-else-if="activeTab === 'files'" :server-id="serverId" />
      <TabHardware v-else-if="activeTab === 'hardware'" :overview="overview" />
      <TabNetwork v-else-if="activeTab === 'network'" :overview="overview" />
      <TabSecurity v-else-if="activeTab === 'security'" :server-id="serverId" :overview="overview" />
      <TabCron v-else-if="activeTab === 'cron'" :overview="overview" />
      <TabSsl v-else-if="activeTab === 'ssl'" :overview="overview" />
      <TabPackages v-else-if="activeTab === 'packages'" :server-id="serverId" :overview="overview" @refresh="fetchData" />
      <TabNotes v-else-if="activeTab === 'notes'" :server-id="serverId" :initial-notes="overview?.notes" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/api/client'

// Sub-components
import TabOverview from '@/components/server/TabOverview.vue'
import TabServices from '@/components/server/TabServices.vue'
import TabTerminal from '@/components/server/TabTerminal.vue'
import TabFiles from '@/components/server/TabFiles.vue'
import TabHardware from '@/components/server/TabHardware.vue'
import TabNetwork from '@/components/server/TabNetwork.vue'
import TabSecurity from '@/components/server/TabSecurity.vue'
import TabCron from '@/components/server/TabCron.vue'
import TabSsl from '@/components/server/TabSsl.vue'
import TabPackages from '@/components/server/TabPackages.vue'
import TabNotes from '@/components/server/TabNotes.vue'

const route = useRoute()
const serverId = computed(() => route.params.id)
const activeTab = ref('overview')
const overview = ref(null)
let pollTimer = null

const tabs = computed(() => [
  { id: 'overview', label: 'Ringkasan', icon: '📊' },
  { id: 'services', label: 'Layanan', icon: '⚙️', badge: (overview.value?.services || []).length || null },
  { id: 'terminal', label: 'Terminal PTY', icon: '💻' },
  { id: 'files', label: 'Berkas (Files)', icon: '📁' },
  { id: 'hardware', label: 'Hardware & SMART', icon: '🖥️' },
  { id: 'network', label: 'Jaringan & Port', icon: '🌐' },
  { id: 'security', label: 'Akun & Sesi', icon: '👤' },
  { id: 'cron', label: 'Cron Jobs', icon: '⏰' },
  { id: 'ssl', label: 'Sertifikat SSL', icon: '🔒' },
  { id: 'packages', label: 'Paket OS (APT)', icon: '📦', badge: overview.value?.apt_upgradable || null },
  { id: 'notes', label: 'Catatan', icon: '📝' },
])

async function fetchData() {
  try {
    const data = await api.get(`/api/servers/${serverId.value}/overview`)
    if (data) overview.value = data
  } catch (err) {
    console.error('Gagal mengambil rincian server:', err)
  }
}

async function rebootHost() {
  if (!confirm(`PERINGATAN: Anda yakin ingin me-reboot host ${overview.value?.server?.hostname}?`)) return
  try {
    await api.post(`/servers/${serverId.value}/host/reboot`)
    alert('Perintah reboot telah dikirim ke agen.')
  } catch (err) {
    alert('Gagal mengirim perintah reboot: ' + err.message)
  }
}

async function poweroffHost() {
  if (!confirm(`PERINGATAN KRITIS: Anda yakin ingin mematikan (Power OFF) host ${overview.value?.server?.hostname}?`)) return
  try {
    await api.post(`/servers/${serverId.value}/host/poweroff`)
    alert('Perintah pemadaman host telah dikirim ke agen.')
  } catch (err) {
    alert('Gagal mengirim perintah pemadaman: ' + err.message)
  }
}

async function updateAgent() {
  if (!confirm(`Kirim perintah self-update agen pada host ${overview.value?.server?.hostname}?`)) return
  try {
    await api.post(`/servers/${serverId.value}/agent/update`)
    alert('Perintah pembaruan agen telah dikirim.')
  } catch (err) {
    alert('Gagal mengirim update agen: ' + err.message)
  }
}

onMounted(() => {
  fetchData()
  pollTimer = setInterval(() => {
    if (!document.hidden && activeTab.value === 'overview') {
      fetchData()
    }
  }, 4000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
