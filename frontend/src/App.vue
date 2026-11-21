<template>
  <div class="min-h-screen bg-[#06090f] text-gray-100 flex flex-col font-sans select-text">
    <!-- TACTICAL NAVBAR -->
    <Navbar
      :active-tab="activeTab"
      :server-count="servers.length"
      :problem-count="activeProblemsCount"
      :ssh-alert-count="activeSSHCount"
      :user="currentUser"
      @nav="handleNav"
      @logout="handleLogout"
      @login-click="showLoginModal = true"
    />

    <!-- MAIN CONTENT VIEWPORT -->
    <main class="flex-1 max-w-[1650px] w-full mx-auto p-3 sm:p-5 pb-24">
      <!-- HALAMAN 1: DASHBOARD (MURNI PASIF: Observasi Makro & Triase Pasif) -->
      <DashboardView
        v-if="activeTab === 'dashboard'"
        :servers="servers"
        :problems="problems"
        @inspect-node="openWorkspace"
        @nav="handleNav"
      />

      <!-- HALAMAN 2: FLEET INVENTORY TABLE (Tabel Rincian Armada Lengkap + Tombol Aksi ala Pantau) -->
      <FleetTableView
        v-else-if="activeTab === 'fleet'"
        :servers="servers"
        @open-workspace="openWorkspace"
        @probe-node="handleProbeNode"
        @more-actions="handleMoreActions"
      />

      <!-- HALAMAN 3: AUDIT TRAIL (Log Akuntabilitas Aksi Operator) -->
      <AuditView
        v-else-if="activeTab === 'audit'"
      />

      <!-- HALAMAN 4: SETTINGS & RBAC (Otoritas & Ambang Batas) -->
      <SettingsView
        v-else-if="activeTab === 'settings'"
      />
    </main>

    <!-- FOOTER STATUS BAR -->
    <footer class="border-t border-gray-800/80 bg-[#090d16] py-2.5 px-6 flex items-center justify-between text-xs text-gray-400 font-mono fixed bottom-0 left-0 right-0 z-30">
      <div class="flex items-center gap-3">
        <span class="text-gray-300 font-bold">PANTAU NOC CONTROL</span>
        <span>·</span>
        <span>{{ t('footer_hotkeys') }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
        <span class="text-emerald-400 font-semibold">{{ t('footer_live_synced') }}</span>
      </div>
    </footer>

    <!-- JENDELA TAKTIS MENGAMBANG: SATU-SATUNYA RANAH KONTROL AKTIF -->
    <ServerWorkspaceModal
      v-if="isWorkspaceOpen"
      :server-id="workspaceServerId"
      :is-open="isWorkspaceOpen"
      :is-minimized="isWorkspaceMinimized"
      :fleet-servers="servers"
      @close="closeWorkspace"
      @minimize="minimizeWorkspace"
      @switch-server="onWorkspaceSwitchServer"
    />

    <!-- WORKSPACE SHELF (Bilah Rak Mengambang untuk Jendela Diminimalkan) -->
    <div
      v-if="isWorkspaceOpen && isWorkspaceMinimized"
      class="fixed bottom-10 right-6 z-40 bg-[#0e1626]/95 border border-cyan-500/50 rounded-xl shadow-2xl p-2 px-4 flex items-center gap-3 backdrop-blur-md transition-all hover:border-cyan-400 group select-none"
    >
      <div
        class="flex items-center gap-2.5 cursor-pointer"
        @click="restoreWorkspace"
        :title="t('tooltip_shelf_open')"
      >
        <span class="text-base">🖥️</span>
        <div>
          <div class="text-xs font-bold text-gray-100 font-mono flex items-center gap-1.5">
            <span
              class="w-2 h-2 rounded-full"
              :class="workspaceHost?.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500'"
            ></span>
            <span>{{ workspaceHost?.hostname || 'Server' }}</span>
            <span class="text-xs text-cyan-300 font-semibold">({{ workspaceHost?.ip_address }})</span>
          </div>
          <div class="text-xs text-gray-400 font-medium">{{ t('shelf_title') }}</div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 border-l border-gray-700/80 pl-2.5 font-mono">
        <button
          @click="restoreWorkspace"
          class="p-1 px-2 rounded bg-blue-600/30 text-cyan-300 hover:bg-blue-600 hover:text-white text-xs transition cursor-pointer font-bold"
          :title="t('shelf_restore')"
        >
          ⛶ {{ t('shelf_restore') }}
        </button>
        <button
          @click="closeWorkspace"
          class="p-1 px-2 rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 text-xs transition cursor-pointer font-bold"
          :title="t('shelf_close')"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- Login Modal -->
    <LoginModal
      v-if="showLoginModal"
      @logged-in="onLoggedIn"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from './i18n'
import Navbar from './components/Navbar.vue'
import DashboardView from './components/dashboard/DashboardView.vue'
import FleetTableView from './components/fleet/FleetTableView.vue'
import AuditView from './components/audit/AuditView.vue'
import SettingsView from './components/settings/SettingsView.vue'
import ServerWorkspaceModal from './components/ServerWorkspaceModal.vue'
import LoginModal from './components/LoginModal.vue'

const { t } = useI18n()

const activeTab = ref('dashboard') // 'dashboard', 'fleet', 'audit', 'settings'
const workspaceServerId = ref(null)
const isWorkspaceOpen = ref(false)
const isWorkspaceMinimized = ref(false)

const currentUser = ref(null)
const showLoginModal = ref(false)

const servers = ref([])
const problems = ref([])
let pollTimer = null

const activeProblemsCount = computed(() => {
  return problems.value.filter((p) => p.is_active).length
})

const activeSSHCount = computed(() => {
  return problems.value.filter((p) => p.is_active && p.key.startsWith('ssh_active_session:')).length
})

const workspaceHost = computed(() => {
  if (!workspaceServerId.value) return null
  return servers.value.find((s) => s.id === workspaceServerId.value) || null
})

function handleNav(tab) {
  activeTab.value = tab
}

function openWorkspace(sid) {
  workspaceServerId.value = sid
  isWorkspaceOpen.value = true
  isWorkspaceMinimized.value = false
}

function minimizeWorkspace() {
  isWorkspaceMinimized.value = true
}

function restoreWorkspace() {
  isWorkspaceMinimized.value = false
}

function closeWorkspace() {
  isWorkspaceOpen.value = false
  isWorkspaceMinimized.value = false
  workspaceServerId.value = null
}

function onWorkspaceSwitchServer(sid) {
  workspaceServerId.value = sid
}

function handleProbeNode(sid) {
  fetchServers()
}

function handleMoreActions(sid, event) {
  openWorkspace(sid)
}

function handleLogout() {
  localStorage.removeItem('pantau_token')
  currentUser.value = null
  showLoginModal.value = true
  closeWorkspace()
}

function onLoggedIn(user) {
  currentUser.value = user
  showLoginModal.value = false
  fetchServers()
  fetchProblems()
}

async function checkAuth() {
  let token = localStorage.getItem('pantau_token')
  if (!token) {
    // Seamless local auto-login for operator session
    try {
      const loginRes = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'operator', password: 'operator' }),
      })
      if (loginRes.ok) {
        const loginData = await loginRes.json()
        if (loginData.access_token) {
          token = loginData.access_token
          localStorage.setItem('pantau_token', token)
          currentUser.value = loginData.user
          showLoginModal.value = false
          fetchServers()
          fetchProblems()
          return
        }
      }
    } catch (e) {
      console.warn('Auto-login fallback:', e)
    }
    showLoginModal.value = true
    return
  }
  try {
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      currentUser.value = data
      fetchServers()
      fetchProblems()
    } else {
      showLoginModal.value = true
    }
  } catch (err) {
    console.error('Auth check error:', err)
  }
}

async function fetchServers() {
  const token = localStorage.getItem('pantau_token')
  if (!token) return
  try {
    const res = await fetch('/api/servers', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      servers.value = data.servers || []
    }
  } catch (err) {
    console.error('Fetch servers error:', err)
  }
}

async function fetchProblems() {
  const token = localStorage.getItem('pantau_token')
  if (!token) return
  try {
    const res = await fetch('/api/problems?active_only=true', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      problems.value = data.problems || []
    }
  } catch (err) {
    console.error('Fetch problems error:', err)
  }
}

function handleGlobalKeydown(e) {
  // If modal is open, let modal handle hotkeys
  if (isWorkspaceOpen.value && !isWorkspaceMinimized.value) return

  // Avoid triggering hotkeys when typing in input
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return

  if (e.key === '1') {
    handleNav('dashboard')
  } else if (e.key === '2') {
    handleNav('fleet')
  } else if (e.key === '3') {
    handleNav('audit')
  } else if (e.key === '4') {
    handleNav('settings')
  }
}

onMounted(() => {
  checkAuth()
  window.addEventListener('keydown', handleGlobalKeydown)
  pollTimer = setInterval(() => {
    if (currentUser.value) {
      fetchServers()
      fetchProblems()
    }
  }, 3000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  if (pollTimer) clearInterval(pollTimer)
})
</script>
