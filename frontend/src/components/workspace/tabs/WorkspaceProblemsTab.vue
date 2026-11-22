<template>
  <div class="space-y-3 font-mono">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">
        // {{ t('ws_incidents_title') }}
      </h3>
      <span class="text-xs text-gray-400">{{ (problems || []).length }} {{ t('active_incidents').toLowerCase() }}</span>
    </div>

    <div v-if="(problems || []).length === 0" class="hud-tactical-card rounded-xl p-8 text-center">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="mb-2 flex justify-center">
        <svg class="w-8 h-8 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 6 9 17l-5-5"/>
        </svg>
      </div>
      <div class="text-xs font-semibold text-gray-200">{{ t('ws_incidents_empty') }}</div>
      <div class="text-xs text-gray-400 mt-1">{{ t('ws_incidents_normal') }}</div>
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="prob in problems"
        :key="prob.id"
        class="hud-tactical-card rounded-xl p-3.5 flex items-start justify-between gap-3"
        :class="prob.key?.startsWith('ssh_active_session:') ? 'border-amber-500/60 bg-amber-950/20' : 'border-gray-800'"
      >
        <div class="flex items-start gap-3">
          <div class="mt-0.5 shrink-0">
            <svg v-if="prob.key?.startsWith('ssh_active_session:')" class="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21 2-2 2m-1.5 1.5L14 9l-2-2-4 4 2 2-3 3-2-2-3 3v4h4l3-3-2-2 3-3 2 2 4-4-2-2 3.5-3.5Z"/></svg>
            <svg v-else class="w-4 h-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <div>
            <div class="text-xs font-bold text-gray-100">{{ prob.message }}</div>
            <div v-if="prob.tip" class="text-xs text-gray-400 mt-1">{{ prob.tip }}</div>
            <div class="text-xs text-gray-500 mt-1">{{ t('ws_detected_since') }} {{ prob.started_at }}</div>
          </div>
        </div>
        <button
          v-if="prob.key?.startsWith('ssh_active_session:')"
          @click="$emit('terminate-ssh-problem', prob.id)"
          class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-800 hover:text-white font-bold text-xs transition cursor-pointer shrink-0"
        >
          {{ t('ws_sever_ssh_btn') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../../i18n'

const { t } = useI18n()

defineProps({
  problems: { type: Array, default: () => [] }
})

defineEmits(['terminate-ssh-problem'])
</script>
