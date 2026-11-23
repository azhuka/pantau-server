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
      @open-terminal="openTerminalDock"
    />

    <!-- MAIN CONTENT VIEWPORT -->
    <main class="flex-1 max-w-[1650px] w-full mx-auto px-3 sm:px-5 pt-3 sm:pt-5 pb-28 sm:pb-32">
      <!-- HALAMAN 1: DASHBOARD (MURNI PASIF: Observasi Makro & Triase Pasif) -->
      <DashboardView
        v-if="activeTab === 'dashboard'"
        :servers="servers"
        :problems="problems"
        @inspect-node="openWorkspace"
        @nav="handleNav"
        @refresh-problems="fetchProblems"
      />

      <!-- HALAMAN 2: ASSET INVENTORY TABLE -->
      <AssetTableView
        v-else-if="activeTab === 'assets'"
        :servers="servers"
        @open-workspace="openWorkspace"
        @open-terminal="openTerminalDock"
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
    <footer class="border-t border-gray-800/80 bg-[#090d16]/95 backdrop-blur-md py-2.5 px-6 flex items-center justify-between text-xs text-gray-400 font-mono fixed bottom-0 left-0 right-0 z-30 shadow-2xl">
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
      :initial-floating-tool="initialFloatingTool"
      :assets-list="servers"
      @close="closeWorkspace"
      @minimize="minimizeWorkspace"
      @switch-server="onWorkspaceSwitchServer"
      @open-terminal="openTerminalDock"
      @server-updated="onServerUpdated"
    />

    <!-- GLOBAL MULTI-TAB WEB TERMINAL DOCK (xterm.js) -->
    <TerminalDockModal
      ref="terminalDockRef"
      :is-open="isTerminalDockOpen"
      :is-minimized="isTerminalDockMinimized"
      :assets-list="servers"
      :initial-server="terminalDockInitialServer"
      @close="closeTerminalDock"
      @minimize="minimizeTerminalDock"
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
        <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect width="20" height="14" x="2" y="3" rx="2"/>
          <line x1="8" y1="21" x2="16" y2="21"/>
          <line x1="12" y1="17" x2="12" y2="21"/>
        </svg>
        <div>
          <div class="text-xs font-bold text-gray-100 font-mono flex items-center gap-1.5">
            <span
              class="w-2 h-2 rounded-full"
              :class="workspaceHost?.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500 radar-critical'"
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
          class="p-1 px-2 rounded bg-cyan-950/80 border border-cyan-600/50 text-cyan-300 hover:bg-cyan-800 hover:text-white text-xs transition cursor-pointer font-bold inline-flex items-center gap-1"
          :title="t('shelf_restore')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/>
            <line x1="3" y1="9" x2="21" y2="9"/>
          </svg>
          <span>{{ t('shelf_restore') }}</span>
        </button>
        <button
          @click="closeWorkspace"
          class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 text-xs transition cursor-pointer font-bold"
          :title="t('shelf_close')"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- TERMINAL DOCK SHELF (Bilah Rak Mengambang untuk Terminal Dock Diminimalkan) -->
    <div
      v-if="isTerminalDockOpen && isTerminalDockMinimized"
      class="fixed bottom-10 z-[20000] bg-[#080d19]/95 border border-cyan-500/50 rounded-xl shadow-2xl p-2 px-4 flex items-center gap-3 backdrop-blur-md transition-all hover:border-cyan-400 group select-none"
      :style="{ right: (isWorkspaceOpen && isWorkspaceMinimized) ? '340px' : '24px' }"
    >
      <div
        class="flex items-center gap-2.5 cursor-pointer"
        @click="restoreTerminalDock"
        title="Restore Multi-Tab Terminal Dock"
      >
        <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="4 17 10 11 4 5"/>
          <line x1="12" y1="19" x2="20" y2="19"/>
        </svg>
        <div>
          <div class="text-xs font-bold text-gray-100 font-mono flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
            <span>{{ t('term_dock_title') || 'TERMINAL DOCK' }}</span>
            <span class="text-xs text-cyan-300 font-semibold">({{ terminalTabsCount }} active)</span>
          </div>
          <div class="text-[11px] text-gray-400 font-medium">{{ t('term_keep_alive') || 'Keep-Alive Session' }}</div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 border-l border-gray-700/80 pl-2.5 font-mono">
        <button
          @click="restoreTerminalDock"
          class="p-1 px-2 rounded bg-cyan-950/80 border border-cyan-600/50 text-cyan-300 hover:bg-cyan-800 hover:text-white text-xs transition cursor-pointer font-bold inline-flex items-center gap-1"
          title="Restore Terminal Dock"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/>
            <line x1="3" y1="9" x2="21" y2="9"/>
          </svg>
          <span>{{ t('term_restore') || 'Restore' }}</span>
        </button>
        <button
          @click="closeTerminalDock"
          class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 text-xs transition cursor-pointer font-bold"
          title="Close All Terminal Sessions"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
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
import AssetTableView from './components/assets/AssetTableView.vue'
import AuditView from './components/audit/AuditView.vue'
import SettingsView from './components/settings/SettingsView.vue'
import ServerWorkspaceModal from './components/ServerWorkspaceModal.vue'
import TerminalDockModal from './components/terminal/TerminalDockModal.vue'
import LoginModal from './components/LoginModal.vue'

const { t } = useI18n()

const activeTab = ref('dashboard') // 'dashboard', 'assets', 'audit', 'settings'
const workspaceServerId = ref(null)
const isWorkspaceOpen = ref(false)
const isWorkspaceMinimized = ref(false)

// Global Multi-Tab Terminal Dock State
const isTerminalDockOpen = ref(false)
const isTerminalDockMinimized = ref(false)
const terminalDockInitialServer = ref(null)
const terminalDockRef = ref(null)

const terminalTabsCount = computed(() => {
  return terminalDockRef.value?.tabs?.length || 0
})

function openTerminalDock(target = null) {
  isTerminalDockOpen.value = true
  isTerminalDockMinimized.value = false
  let srv = null
  let initialPath = ''
  if (target && target.server) {
    srv = target.server
    initialPath = target.initialPath || target.workingDirectory || ''
  } else if (target) {
    srv = target
    initialPath = target.workingDirectory || ''
  } else {
    srv = servers.value.length > 0 ? servers.value[0] : null
  }

  if (srv) {
    const srvWithDir = { ...srv, workingDirectory: initialPath }
    terminalDockInitialServer.value = srvWithDir
    if (terminalDockRef.value) {
      terminalDockRef.value.openNewTabForServer(srvWithDir)
    }
  }
}

function minimizeTerminalDock() {
  isTerminalDockMinimized.value = true
}

function restoreTerminalDock() {
  isTerminalDockMinimized.value = false
}

function closeTerminalDock() {
  isTerminalDockOpen.value = false
  isTerminalDockMinimized.value = false
  terminalDockInitialServer.value = null
}

function onServerUpdated(updated) {
  if (!updated || !updated.id) return
  const idx = servers.value.findIndex(s => s.id === updated.id)
  if (idx !== -1) {
    servers.value[idx] = { ...servers.value[idx], ...updated }
  }
}

const currentUser = ref(null)
const showLoginModal = ref(false)

const servers = ref([])
const problems = ref([])
let pollTimer = null

const activeProblemsCount = computed(() => {
  return problems.value.filter((p) => p.is_active && !p.is_ignored).length
})

const activeSSHCount = computed(() => {
  return problems.value.filter((p) => p.is_active && !p.is_ignored && p.key.startsWith('ssh_active_session:')).length
})

const workspaceHost = computed(() => {
  if (!workspaceServerId.value) return null
  return servers.value.find((s) => s.id === workspaceServerId.value) || null
})

function handleNav(tab) {
  activeTab.value = tab
}

const initialFloatingTool = ref(null)

function openWorkspace(sid, tool = null) {
  workspaceServerId.value = sid
  initialFloatingTool.value = tool
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

function checkUrlStandalone() {
  const urlParams = new URLSearchParams(window.location.search)
  const standalone = urlParams.get('standalone')
  const sid = parseInt(urlParams.get('sid'))
  if (standalone === 'terminal') {
    const targetServer = sid ? (servers.value.find((s) => s.id === sid) || { id: sid, hostname: `Server #${sid}` }) : null
    openTerminalDock(targetServer)
  } else if (standalone && sid) {
    openWorkspace(sid, standalone)
  }
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
          checkUrlStandalone()
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
      checkUrlStandalone()
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
    handleNav('assets')
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
