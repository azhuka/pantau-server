<template>
  <div class="space-y-4 font-mono">
    <!-- Sesi SSH Aktif -->
    <div class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_ssh_active_title') }}</h3>
        <span
          v-if="(activeSSHSessions || []).length > 0"
          class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 radar-warning"
        >
          {{ activeSSHSessions.length }} {{ t('ws_ssh_sessions_count') }}
        </span>
      </div>
      <div v-if="(activeSSHSessions || []).length === 0" class="text-xs text-gray-400 py-6 text-center">
        {{ t('ws_ssh_empty') }}
      </div>
      <div v-else class="space-y-2">
        <div
          v-for="(s, idx) in activeSSHSessions"
          :key="idx"
          class="p-3 bg-amber-950/20 border border-amber-700/60 rounded-lg flex items-center justify-between"
        >
          <div class="flex items-center gap-3">
            <svg class="w-5 h-5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21 2-2 2m-1.5 1.5L14 9l-2-2-4 4 2 2-3 3-2-2-3 3v4h4l3-3-2-2 3-3 2 2 4-4-2-2 3.5-3.5Z"/>
            </svg>
            <div>
              <div class="text-xs font-bold text-amber-300">
                {{ s.user }} <span class="text-gray-400 font-normal">{{ t('ws_connected_from') }}</span> {{ s.from }}
              </div>
              <div class="text-xs text-gray-400 mt-1">
                TTY: {{ s.tty }} · {{ t('dash_col_time') }}: {{ s.time || '-' }}
              </div>
            </div>
          </div>
          <button
            @click="$emit('terminate-ssh', s.user, s.tty)"
            class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white font-bold text-xs transition cursor-pointer flex items-center gap-1.5"
            :title="`Terminate active SSH session for user ${s.user} on ${s.tty}`"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>
            </svg>
            <span>{{ t('ws_sever_ssh_btn') }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Akun Pengguna Lokal -->
    <div class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">// {{ t('ws_accounts_title') }}</h3>
      <div class="overflow-x-auto max-h-[350px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
            <tr class="text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('ws_col_username') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_uid') || 'UID' }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_home') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_shell') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(acc, idx) in accountsList || []" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 px-3 font-semibold text-gray-200">{{ acc.user || acc.name }}</td>
              <td class="py-2.5 px-3 text-gray-400">{{ acc.uid || '-' }}</td>
              <td class="py-2.5 px-3 text-gray-300">{{ acc.home || '-' }}</td>
              <td class="py-2.5 px-3 text-cyan-400">{{ acc.shell || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../../i18n'

const { t } = useI18n()

defineProps({
  activeSSHSessions: { type: Array, default: () => [] },
  accountsList: { type: Array, default: () => [] }
})

defineEmits(['terminate-ssh'])
</script>
