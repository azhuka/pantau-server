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
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <span class="px-1.5 py-0.2 rounded text-[10px] font-extrabold uppercase border" :class="severityBadgeClass(prob.severity)">
                {{ prob.severity || 'INFO' }}
              </span>
              <div class="text-xs font-bold text-gray-100">{{ formatIncidentMessage(prob, locale) }}</div>
            </div>
            <div v-if="formatIncidentTip(prob, locale)" class="text-xs text-gray-400 mt-0.5">{{ formatIncidentTip(prob, locale) }}</div>

            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              <span class="text-xs text-gray-500">{{ t('ws_detected_since') }} {{ formatIncidentTime(prob.started_at) }}</span>
              <span
                v-if="prob.acknowledged_by"
                class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1"
                :title="t('dash_acked_by', { user: prob.acknowledged_by })"
              >
                ✓ {{ t('dash_badge_handled') }}
              </span>
              <span
                v-if="prob.is_ignored"
                class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-gray-700/50 text-gray-300 border border-gray-600 flex items-center gap-1"
                :title="prob.ignored_reason || 'Ignored'"
              >
                <svg class="w-3 h-3 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
                <span>{{ t('inc_ignored_badge') }}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2 shrink-0">
          <button
            v-if="prob.key?.startsWith('ssh_active_session:') && !isViewer"
            @click="$emit('terminate-ssh-problem', prob.id)"
            class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-800 hover:text-white font-bold text-xs transition cursor-pointer"
          >
            {{ t('ws_sever_ssh_btn') }}
          </button>

          <!-- Ack Button / Handled State -->
          <button
            v-if="!prob.acknowledged_by && !isViewer"
            @click="$emit('ack-problem', prob.id)"
            class="px-2.5 py-1 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-700/80 hover:bg-emerald-800 hover:text-white font-bold text-xs transition cursor-pointer flex items-center gap-1 shadow-sm"
            :title="t('inc_btn_ack')"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>{{ t('inc_btn_ack') }}</span>
          </button>
          <span
            v-else-if="prob.acknowledged_by"
            class="px-2.5 py-1 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-700/60 font-bold text-xs flex items-center gap-1 cursor-default select-none"
            :title="t('dash_acked_by', { user: prob.acknowledged_by })"
          >
            <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>✓ {{ t('dash_badge_handled') }}</span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../../i18n'
import { formatIncidentMessage, formatIncidentTip, formatIncidentTime } from '../../../utils/formatters'

const { t, locale } = useI18n()

const props = defineProps({
  problems: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null }
})

defineEmits(['terminate-ssh-problem', 'ack-problem'])

const isViewer = computed(() => {
  const r = (props.currentUser?.role || '').toLowerCase()
  return !props.currentUser || ['viewer', 'guest', 'tamu'].includes(r)
})

function severityBadgeClass(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'danger') return 'bg-rose-950/80 text-rose-300 border-rose-700'
  if (s === 'critical' || s === 'average') return 'bg-orange-950/80 text-orange-300 border-orange-700'
  if (s === 'warning') return 'bg-amber-950/80 text-amber-300 border-amber-700'
  return 'bg-cyan-950/80 text-cyan-300 border-cyan-700'
}
</script>
