<template>
  <header class="bg-[#0c121e] border-b border-gray-800/80 px-5 h-14 flex items-center justify-between sticky top-0 z-40 select-none backdrop-blur-md">
    <!-- LEFT: BRAND & TACTICAL NAVIGATION -->
    <div class="flex items-center gap-6">
      <!-- Cyber Brand -->
      <div class="flex items-center gap-3 cursor-pointer" @click="$emit('nav', 'dashboard')">
        <div class="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center font-black text-cyan-400 text-base shadow-[0_0_12px_rgba(56,189,248,0.3)]">
          ⛊
        </div>
        <div>
          <div class="font-bold text-sm tracking-wide text-gray-100 flex items-center gap-2">
            <span>{{ t('app_name') }}</span>
            <span class="text-xs font-mono font-bold px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800/60">
              v0.1.0
            </span>
          </div>
          <div class="text-xs text-gray-400 tracking-wider font-medium">
            CYBER NOC RECON & COMMAND
          </div>
        </div>
      </div>

      <!-- 4-VIEW TACTICAL NAVIGATION LINKS -->
      <nav class="hidden md:flex items-center gap-1.5 border-l border-gray-800/80 pl-5 text-sm">
        <!-- 1: DASHBOARD -->
        <button
          @click="$emit('nav', 'dashboard')"
          :class="[
            'px-3.5 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-2 font-medium',
            activeTab === 'dashboard'
              ? 'bg-blue-600/25 text-cyan-300 border border-blue-500/50 font-bold shadow-sm'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
          ]"
        >
          <span>📊</span>
          <span>{{ t('nav_dashboard') }}</span>
        </button>

        <!-- 2: FLEET INVENTORY -->
        <button
          @click="$emit('nav', 'fleet')"
          :class="[
            'px-3.5 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-2 font-medium',
            activeTab === 'fleet'
              ? 'bg-blue-600/25 text-cyan-300 border border-blue-500/50 font-bold shadow-sm'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
          ]"
        >
          <span>🖥️</span>
          <span>{{ t('nav_fleet') }}</span>
          <span
            v-if="serverCount"
            class="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 font-mono font-bold ml-0.5"
          >
            {{ serverCount }}
          </span>
        </button>

        <!-- 3: AUDIT TRAIL -->
        <button
          @click="$emit('nav', 'audit')"
          :class="[
            'px-3.5 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-2 font-medium',
            activeTab === 'audit'
              ? 'bg-blue-600/25 text-cyan-300 border border-blue-500/50 font-bold shadow-sm'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
          ]"
        >
          <span>📋</span>
          <span>{{ t('nav_audit') }}</span>
        </button>

        <!-- 4: SETTINGS & RBAC -->
        <button
          @click="$emit('nav', 'settings')"
          :class="[
            'px-3.5 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-2 font-medium',
            activeTab === 'settings'
              ? 'bg-blue-600/25 text-cyan-300 border border-blue-500/50 font-bold shadow-sm'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
          ]"
        >
          <span>⚙️</span>
          <span>{{ t('nav_settings') }}</span>
        </button>
      </nav>
    </div>

    <!-- RIGHT: HEARTBEAT WAVE, I18N SWITCHER, OPERATOR PROFILE -->
    <div class="flex items-center gap-3">
      <!-- Live Heartbeat Waveform Beacon -->
      <div class="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#070b14] border border-gray-800 text-xs font-mono font-semibold text-emerald-400">
        <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 beacon-live"></span>
        <span class="tracking-wider">FEED LIVE</span>
      </div>

      <!-- Multi-Language i18n Switcher Button (EN / ID) -->
      <button
        @click="toggleLocale"
        class="px-3 py-1.5 rounded-lg bg-[#111a2c] border border-gray-700/80 hover:border-cyan-400/60 text-xs font-bold text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1.5 shadow-sm"
        :title="locale === 'en' ? 'Switch Language (to Bahasa Indonesia)' : 'Ganti Bahasa (ke English)'"
      >
        <span>🌐</span>
        <span class="tracking-wider">{{ locale.toUpperCase() }}</span>
      </button>

      <!-- Operator User Badge -->
      <div v-if="user" class="flex items-center gap-2.5 border-l border-gray-800/80 pl-3.5">
        <div class="text-right">
          <div class="text-xs font-bold text-gray-100">{{ user.username }}</div>
          <div class="text-[11px] font-semibold text-cyan-400 font-mono uppercase">{{ user.role }}</div>
        </div>
        <button
          @click="$emit('logout')"
          class="text-xs p-1.5 rounded-lg border border-gray-800 bg-gray-900/60 text-gray-400 hover:bg-rose-950/40 hover:text-rose-300 hover:border-rose-800/50 transition cursor-pointer"
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
          class="text-xs px-3.5 py-1.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-500 transition cursor-pointer"
        >
          {{ t('nav_login') }}
        </button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
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
