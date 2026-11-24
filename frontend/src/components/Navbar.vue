<template>
  <header class="bg-[#080d19]/95 border-b border-cyan-500/20 px-4 sm:px-6 h-14 flex items-center justify-between sticky top-0 z-40 select-none backdrop-blur-md shadow-[0_4px_20px_rgba(0,0,0,0.6)]">
    <!-- LEFT: BRAND & TACTICAL NAVIGATION -->
    <div class="flex items-center gap-6">
      <!-- Cyber Brand with Tactical HUD Moniker -->
      <div class="flex items-center gap-3 cursor-pointer group" @click="$emit('nav', 'dashboard')">
        <div class="w-8 h-8 rounded bg-cyan-950/60 border border-cyan-400/50 flex items-center justify-center text-cyan-300 shadow-[0_0_12px_rgba(56,189,248,0.35)] group-hover:border-cyan-300 transition-all">
          <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
            <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
            <line x1="6" y1="6" x2="6.01" y2="6"/>
            <line x1="6" y1="18" x2="6.01" y2="18"/>
          </svg>
        </div>
        <div>
          <div class="font-bold text-sm tracking-wider text-gray-100 flex items-center gap-2 font-mono">
            <span class="text-cyan-400 font-extrabold">{{ t('app_name') }}</span>
            <span class="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 tracking-normal">
              v0.1.51
            </span>
          </div>
          <div class="text-[10px] text-gray-400 tracking-widest font-mono uppercase flex items-center gap-1.5">
            <span class="text-cyan-500/80">//</span>
            <span>ASSET TELEMETRY &amp; NOC CONTROL</span>
          </div>
        </div>
      </div>

      <!-- 4-VIEW TACTICAL NAVIGATION (Segmented Deck Buttons) -->
      <nav class="hidden md:flex items-center gap-1 border-l border-gray-800/80 pl-5 text-xs font-mono">
        <!-- 1: DASHBOARD -->
        <button
          @click="$emit('nav', 'dashboard')"
          :class="[
            'px-3 py-1.5 rounded transition-all cursor-pointer flex items-center gap-2 font-semibold tracking-wide border',
            activeTab === 'dashboard'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span class="text-cyan-400/70">01 //</span>
          <span>{{ t('nav_dashboard') }}</span>
        </button>

        <!-- 2: ASSET INVENTORY -->
        <button
          @click="$emit('nav', 'assets')"
          :class="[
            'px-3 py-1.5 rounded transition-all cursor-pointer flex items-center gap-2 font-semibold tracking-wide border',
            activeTab === 'assets'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span class="text-cyan-400/70">02 //</span>
          <span>{{ t('nav_assets') }}</span>
          <span
            v-if="serverCount"
            class="text-[11px] px-1.5 py-0.2 rounded bg-gray-800/90 text-cyan-300 font-bold ml-0.5 border border-cyan-800/40"
          >
            {{ serverCount }}
          </span>
        </button>

        <!-- 3: AUDIT TRAIL -->
        <button
          v-if="user?.is_master_admin || user?.permissions?.can_audit"
          @click="$emit('nav', 'audit')"
          :class="[
            'px-3 py-1.5 rounded transition-all cursor-pointer flex items-center gap-2 font-semibold tracking-wide border',
            activeTab === 'audit'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span class="text-cyan-400/70">03 //</span>
          <span>{{ t('nav_audit') }}</span>
        </button>

        <!-- 4: SETTINGS & RBAC -->
        <button
          v-if="user?.is_master_admin || user?.permissions?.can_manage_users || user?.permissions?.can_manage_viewers"
          @click="$emit('nav', 'settings')"
          :class="[
            'px-3 py-1.5 rounded transition-all cursor-pointer flex items-center gap-2 font-semibold tracking-wide border',
            activeTab === 'settings'
              ? 'bg-cyan-950/50 text-cyan-300 border-cyan-500/60 font-bold shadow-[0_0_10px_rgba(56,189,248,0.2)]'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <span class="text-cyan-400/70">04 //</span>
          <span>{{ t('nav_settings') }}</span>
        </button>
      </nav>
    </div>

    <!-- RIGHT: RADAR STATUS, I18N SWITCHER, OPERATOR PROFILE -->
    <div class="flex items-center gap-3">
      <!-- Live Heartbeat Radar Beacon -->
      <div class="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-[#060a14] border border-cyan-900/40 text-xs font-mono font-semibold text-emerald-400">
        <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live beacon-radar"></span>
        <span class="tracking-wider text-[11px]">FEED // LIVE</span>
      </div>

      <!-- Multi-Language i18n Switcher Button (EN / ID) -->
      <button
        @click="toggleLocale"
        class="px-2.5 py-1 rounded bg-[#0e1628] border border-cyan-500/30 hover:border-cyan-400 text-xs font-mono font-bold text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1.5 shadow-sm"
        :title="t('nav_switch_lang')"
      >
        <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span class="tracking-widest">{{ locale.toUpperCase() }}</span>
      </button>

      <!-- Operator User Badge -->
      <div v-if="user" class="flex items-center gap-2.5 border-l border-gray-800 pl-3.5">
        <div class="text-right">
          <div class="text-xs font-bold text-gray-100 font-mono leading-none mb-1">{{ user.username }}</div>
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
        <button
          @click="$emit('logout')"
          class="text-xs p-1.5 rounded border border-gray-800 bg-gray-900/60 text-gray-400 hover:bg-rose-950/40 hover:text-rose-300 hover:border-rose-800/50 transition cursor-pointer"
          :title="t('nav_logout')"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
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
</template>

<script setup>
import { useI18n } from '../i18n'

const props = defineProps({
  activeTab: String,
  serverCount: Number,
  problemCount: Number,
  sshAlertCount: Number,
  user: Object,
})

defineEmits(['nav', 'logout', 'login-click'])

const { locale, toggleLocale, t } = useI18n()
</script>
