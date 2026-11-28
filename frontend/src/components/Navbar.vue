<template>
  <header class="bg-[#080d19]/95 border-b border-cyan-500/20 px-4 sm:px-6 h-14 flex items-center justify-between sticky top-0 z-40 select-none backdrop-blur-md shadow-[0_4px_20px_rgba(0,0,0,0.6)]">
    <!-- LEFT: BRAND & TACTICAL NAVIGATION -->
    <div class="flex items-center gap-3 min-w-0">
      <!-- Mobile Drawer Trigger -->
      <button
        type="button"
        @click="mobileMenuOpen = !mobileMenuOpen"
        class="md:hidden p-1.5 rounded border border-gray-800 bg-gray-900/70 text-gray-300 hover:text-white cursor-pointer"
        title="Open Navigation Menu"
        aria-label="Open Navigation Menu"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <!-- Brand -->
      <div class="flex items-center gap-2.5 cursor-pointer group shrink-0" @click="$emit('nav', 'dashboard')">
        <div class="w-8 h-8 rounded bg-cyan-950/60 border border-cyan-400/50 flex items-center justify-center text-cyan-300 shadow-[0_0_12px_rgba(56,189,248,0.35)] group-hover:border-cyan-300 transition-all shrink-0">
          <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
            <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
            <line x1="6" y1="6" x2="6.01" y2="6"/>
            <line x1="6" y1="18" x2="6.01" y2="18"/>
          </svg>
        </div>
        <div class="shrink-0">
          <div class="font-bold text-sm tracking-wider text-gray-100 flex items-center gap-2 font-mono whitespace-nowrap">
            <span class="text-cyan-400 font-extrabold">{{ t('app_name') }}</span>
            <span class="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 tracking-normal">
              v0.1.122
            </span>
          </div>
          <div class="text-[10px] text-gray-400 tracking-wider font-mono uppercase whitespace-nowrap">
            ASSET TELEMETRY &amp; NOC CONTROL
          </div>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="hidden md:flex items-center gap-1 border-l border-gray-800/80 pl-3 text-xs font-mono overflow-x-auto no-scrollbar">
        <!-- 1: DASHBOARD -->
        <button
          @click="$emit('nav', 'dashboard')"
          :class="[
            'px-2.5 py-1.5 rounded transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wide border whitespace-nowrap shrink-0',
            activeTab === 'dashboard'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span>{{ t('nav_dashboard') }}</span>
        </button>

        <!-- 2: INCIDENTS -->
        <button
          @click="$emit('nav', 'incidents')"
          :class="[
            'px-2.5 py-1.5 rounded transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wide border whitespace-nowrap shrink-0',
            activeTab === 'incidents'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span>{{ t('nav_incidents') }}</span>
        </button>

        <!-- 3: ASSET INVENTORY -->
        <button
          @click="$emit('nav', 'assets')"
          :class="[
            'px-2.5 py-1.5 rounded transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wide border whitespace-nowrap shrink-0',
            activeTab === 'assets'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span>{{ t('nav_assets') }}</span>
        </button>

        <!-- 4: AUDIT TRAIL -->
        <button
          v-if="user?.is_master_admin || user?.permissions?.can_audit"
          @click="$emit('nav', 'audit')"
          :class="[
            'px-2.5 py-1.5 rounded transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wide border whitespace-nowrap shrink-0',
            activeTab === 'audit'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span>{{ t('nav_audit') }}</span>
        </button>

        <!-- 5: SETTINGS & RBAC -->
        <button
          v-if="user?.is_master_admin || user?.permissions?.can_manage_users || user?.permissions?.can_manage_viewers"
          @click="$emit('nav', 'settings')"
          :class="[
            'px-2.5 py-1.5 rounded transition-all cursor-pointer flex items-center gap-1.5 font-semibold tracking-wide border whitespace-nowrap shrink-0',
            activeTab === 'settings'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span>{{ t('nav_settings') }}</span>
        </button>
      </nav>
    </div>

    <!-- RIGHT: LIVE STATUS & OPERATOR PROFILE -->
    <div class="flex items-center gap-2 shrink-0">
      <!-- Live Heartbeat Beacon -->
      <div class="hidden xl:flex items-center gap-2 px-2.5 py-1 rounded bg-[#060a14] border border-cyan-900/40 text-xs font-mono font-semibold text-emerald-400 whitespace-nowrap shrink-0">
        <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live beacon-radar shrink-0"></span>
        <span class="tracking-wider text-[11px]">LIVE</span>
      </div>

      <!-- Operator Profile Dropdown -->
      <div v-if="user" ref="userMenuRef" class="relative border-l border-gray-800 pl-3 shrink-0">
        <button
          type="button"
          @click="userMenuOpen = !userMenuOpen"
          class="flex items-center gap-2 px-2 py-1 rounded border border-transparent hover:border-gray-700/80 hover:bg-gray-900/60 transition cursor-pointer"
          :aria-expanded="userMenuOpen"
          aria-haspopup="menu"
        >
          <div class="text-right">
            <div class="text-xs font-bold text-gray-100 font-mono leading-none mb-1 whitespace-nowrap">{{ user.username }}</div>
            <div class="flex items-center justify-end">
              <span
                v-if="user.is_master_admin || user.role === 'master_admin'"
                class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-cyan-950/90 text-cyan-300 border border-cyan-500/50 tracking-wider"
              >
                MASTER ADMIN
              </span>
              <span
                v-else-if="user.is_operator || user.role === 'operator'"
                class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 tracking-wider"
              >
                OPERATOR
              </span>
              <span
                v-else-if="user.is_viewer || user.role === 'viewer'"
                class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-slate-800/90 text-slate-300 border border-slate-600/50 tracking-wider"
              >
                VIEWER
              </span>
              <span
                v-else
                class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-gray-800 text-gray-300 border border-gray-700 tracking-wider uppercase"
              >
                {{ user.role }}
              </span>
            </div>
          </div>
          <svg
            class="w-3.5 h-3.5 text-gray-400 transition-transform"
            :class="userMenuOpen ? 'rotate-180 text-cyan-300' : ''"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        <!-- Floating Operator Menu -->
        <div
          v-if="userMenuOpen"
          role="menu"
          class="absolute right-0 mt-2 w-48 rounded-lg border border-cyan-500/30 bg-[#0b1220] shadow-2xl py-1.5 font-mono text-xs z-50"
        >
          <button
            type="button"
            role="menuitem"
            @click="userMenuOpen = false; $emit('open-theme')"
            class="w-full px-3 py-2 text-left text-gray-200 hover:bg-cyan-950/50 hover:text-cyan-300 flex items-center gap-2.5 transition cursor-pointer"
          >
            <svg class="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
            </svg>
            <span>UI Settings</span>
          </button>
          <div class="my-1 border-t border-gray-800/80"></div>
          <button
            type="button"
            role="menuitem"
            @click="userMenuOpen = false; $emit('logout')"
            class="w-full px-3 py-2 text-left text-rose-300 hover:bg-rose-950/40 hover:text-rose-200 flex items-center gap-2.5 transition cursor-pointer"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>{{ t('nav_logout') }}</span>
          </button>
        </div>
      </div>

      <div v-else>
        <button
          @click="$emit('login-click')"
          class="text-xs px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-mono font-semibold transition cursor-pointer border border-cyan-500/40"
        >
          {{ t('nav_login') }}
        </button>
      </div>
    </div>
  </header>

  <!-- Mobile Navigation Drawer -->
  <div
    v-if="mobileMenuOpen"
    class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm md:hidden flex"
    @click.self="mobileMenuOpen = false"
  >
    <div class="w-64 bg-[#080d19] border-r border-cyan-500/30 h-full p-4 flex flex-col gap-2 font-mono text-xs shadow-2xl">
      <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-1">
        <span class="font-bold text-cyan-400">{{ t('app_name') }}</span>
        <button type="button" @click="mobileMenuOpen = false" class="p-1 text-gray-400 hover:text-white cursor-pointer" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <button
        v-for="item in mobileNavItems"
        :key="item.id"
        type="button"
        @click="$emit('nav', item.id); mobileMenuOpen = false"
        :class="[
          'w-full text-left px-3 py-2 rounded border transition cursor-pointer font-semibold',
          activeTab === item.id
            ? 'bg-cyan-950/60 text-cyan-300 border-cyan-500/50'
            : 'text-gray-300 border-transparent hover:bg-gray-800/60'
        ]"
      >
        {{ item.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({
  activeTab: String,
  serverCount: Number,
  problemCount: Number,
  sshAlertCount: Number,
  user: Object,
})

defineEmits(['nav', 'logout', 'login-click', 'open-theme'])

const { t } = useI18n()
const mobileMenuOpen = ref(false)
const userMenuOpen = ref(false)
const userMenuRef = ref(null)

function handleDocClick(e) {
  if (userMenuOpen.value && userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    userMenuOpen.value = false
  }
}

function handleDocKeydown(e) {
  if (userMenuOpen.value && e.key === 'Escape') {
    userMenuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocClick)
  document.addEventListener('keydown', handleDocKeydown)
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocClick)
  document.removeEventListener('keydown', handleDocKeydown)
})

const mobileNavItems = computed(() => {
  const items = [
    { id: 'dashboard', label: t('nav_dashboard') },
    { id: 'incidents', label: t('nav_incidents') },
    { id: 'assets', label: t('nav_assets') },
  ]
  if (props.user?.is_master_admin || props.user?.permissions?.can_audit) {
    items.push({ id: 'audit', label: t('nav_audit') })
  }
  if (props.user?.is_master_admin || props.user?.permissions?.can_manage_users || props.user?.permissions?.can_manage_viewers) {
    items.push({ id: 'settings', label: t('nav_settings') })
  }
  return items
})
</script>
