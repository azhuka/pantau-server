<template>
  <header class="bg-noc-card/95 backdrop-blur border-b border-noc-border sticky top-0 z-50">
    <div class="max-w-[1720px] mx-auto px-4 h-12 flex items-center justify-between text-xs">
      <!-- Left: Brand & Nav Links -->
      <div class="flex items-center gap-6">
        <router-link to="/dashboard" class="flex items-center gap-2 font-bold text-sm text-noc-text hover:text-noc-cyan transition-colors">
          <div class="w-6 h-6 rounded bg-noc-cyan/20 border border-noc-cyan/40 flex items-center justify-center text-noc-cyan font-mono text-xs shadow-sm">
            PS
          </div>
          <span class="tracking-tight">PANTAU<span class="text-noc-cyan font-normal ml-1">SERVER</span></span>
        </router-link>

        <nav class="hidden md:flex items-center gap-1 font-medium text-noc-dim">
          <router-link
            to="/dashboard"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04]"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            Dasbor
          </router-link>
          <router-link
            to="/servers"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04]"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            Server
          </router-link>
          <router-link
            to="/probing"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04]"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            Probing
          </router-link>
          <router-link
            to="/maintenance"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04]"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            Pemeliharaan
          </router-link>
          <router-link
            to="/logs"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04]"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            Audit Log
          </router-link>
          <router-link
            v-if="authStore.isMasterAdmin"
            to="/master-control"
            class="px-2.5 py-1 rounded transition-colors hover:text-noc-text hover:bg-white/[0.04] flex items-center gap-1.5"
            active-class="text-noc-cyan bg-noc-cyan/10 font-semibold"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-noc-cyan animate-pulse"></span>
            Master Control
          </router-link>
        </nav>
      </div>

      <!-- Right: Clock, Alert Badge, User Dropdown -->
      <div class="flex items-center gap-3">
        <!-- Live Clock -->
        <div class="hidden sm:flex items-center gap-1.5 font-mono text-[11px] text-noc-muted bg-noc-bg/80 px-2 py-0.5 rounded border border-noc-border/50">
          <span class="text-noc-dim">UTC</span>
          <span class="text-noc-text font-medium">{{ utcClock }}</span>
        </div>

        <!-- Incidents Counter Badge -->
        <router-link
          to="/dashboard"
          v-if="problemStore.summary.total_active > 0"
          class="flex items-center gap-1.5 px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 font-mono text-[11px] font-semibold hover:bg-rose-500/20 transition-colors"
          title="Insiden Aktif Membutuhkan Perhatian"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping"></span>
          <span>{{ problemStore.summary.total_active }} Insiden</span>
        </router-link>

        <!-- User Menu Dropdown -->
        <div class="relative" ref="menuRef">
          <button
            @click="menuOpen = !menuOpen"
            class="flex items-center gap-2 px-2 py-1 rounded hover:bg-white/[0.05] transition-colors focus:outline-none"
          >
            <div class="w-6 h-6 rounded-full bg-noc-surface border border-noc-border flex items-center justify-center font-semibold text-[11px] text-noc-cyan uppercase">
              {{ authStore.user?.username?.[0] || 'O' }}
            </div>
            <div class="hidden md:block text-left text-xs leading-none">
              <div class="font-medium text-noc-text">{{ authStore.user?.username || 'Operator' }}</div>
              <div class="text-[10px] text-noc-muted capitalize mt-0.5">{{ authStore.user?.role?.replace('_', ' ') || 'NOC' }}</div>
            </div>
          </button>

          <!-- Dropdown items -->
          <div
            v-if="menuOpen"
            class="absolute right-0 mt-1 w-44 bg-noc-card border border-noc-border rounded-lg shadow-xl py-1 z-50 text-xs"
          >
            <div class="px-3 py-1.5 border-b border-noc-border/50 text-noc-muted text-[10px]">
              Masuk sebagai <strong class="text-noc-text">{{ authStore.user?.username }}</strong>
            </div>
            <router-link
              to="/profile"
              @click="menuOpen = false"
              class="block px-3 py-1.5 text-noc-text hover:bg-white/[0.05] transition-colors"
            >
              Profil & Keamanan 2FA
            </router-link>
            <router-link
              v-if="authStore.isMasterAdmin"
              to="/users"
              @click="menuOpen = false"
              class="block px-3 py-1.5 text-noc-text hover:bg-white/[0.05] transition-colors"
            >
              Kelola Pengguna
            </router-link>
            <div class="my-1 border-t border-noc-border/50"></div>
            <button
              @click="handleLogout"
              class="w-full text-left px-3 py-1.5 text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              Keluar (Logout)
            </button>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useProblemStore } from '@/stores/problems'

const authStore = useAuthStore()
const problemStore = useProblemStore()
const menuOpen = ref(false)
const utcClock = ref('--:--:--')
let clockTimer = null

function updateClock() {
  const now = new Date()
  utcClock.value = now.toISOString().substring(11, 19)
}

function handleLogout() {
  menuOpen.value = false
  authStore.logout()
}

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  problemStore.startPolling(8000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  problemStore.stopPolling()
})
</script>
