<template>
  <div
    v-if="isOpen && problem"
    id="problem-detail-modal"
    class="fixed inset-0 z-[20000] bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
    @click.self="$emit('close')"
  >
    <div class="hud-tactical-card rounded-xl max-w-2xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-cyan-500/40">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Header -->
      <div class="p-4 border-b border-gray-800 flex items-center justify-between shrink-0 bg-[#070c18]">
        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <h2 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">{{ t('pdm_title') }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-[10px] px-2 py-0.5 rounded font-bold uppercase" :class="sevBadgeClass">
            {{ t(`sev_${problem.severity || 'info'}`) || problem.severity || 'INFO' }}
          </span>
          <button
            type="button"
            class="p-1 text-gray-400 hover:text-white rounded hover:bg-gray-800/70 transition-colors cursor-pointer"
            title="Close"
            aria-label="Close"
            @click="$emit('close')"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Content Sections -->
      <div class="p-5 overflow-y-auto space-y-4 text-xs flex-1">
        <!-- Target Host & Message -->
        <div class="p-3 rounded-lg bg-cyan-950/20 border border-cyan-900/40">
          <div class="text-[11px] text-gray-400 uppercase font-bold">{{ t('pdm_target_host') }}</div>
          <div class="text-sm font-bold text-cyan-300 mt-0.5">{{ problem.hostname || `Server #${problem.server_id}` }}</div>
          <div class="text-xs text-gray-200 mt-1 font-medium leading-relaxed">{{ formatIncidentMessage(problem, locale) }}</div>
        </div>

        <!-- 1. Root Cause -->
        <div class="space-y-1">
          <div class="text-amber-400 font-bold uppercase text-[11px] flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span>{{ t('pdm_root_cause') }}</span>
          </div>
          <p class="text-gray-300 leading-relaxed bg-[#060a14] p-3 rounded border border-gray-800">{{ rootCauseText }}</p>
        </div>

        <!-- 2. Operational Impact -->
        <div class="space-y-1">
          <div class="text-rose-400 font-bold uppercase text-[11px] flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/></svg>
            <span>{{ t('pdm_operational_impact') }}</span>
          </div>
          <p class="text-gray-300 leading-relaxed bg-[#060a14] p-3 rounded border border-gray-800">{{ impactText }}</p>
        </div>

        <!-- 3. Recommendations & CLI -->
        <div class="space-y-1">
          <div class="text-emerald-400 font-bold uppercase text-[11px] flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
            <span>{{ t('pdm_recommendations') }}</span>
          </div>
          <div class="bg-[#060a14] p-3 rounded border border-gray-800 space-y-2">
            <p class="text-gray-300 leading-relaxed">{{ formatIncidentTip(problem, locale) || recommendationText }}</p>
            <div v-if="cliCommand" class="mt-2">
              <div class="flex items-center justify-between text-[10px] text-gray-500 mb-1">
                <span>{{ t('pdm_cli_label') }}</span>
                <button @click="copyCli" class="text-cyan-400 hover:text-cyan-300 transition cursor-pointer font-bold">
                  {{ copied ? t('pdm_cmd_copied') : t('pdm_copy_cmd') }}
                </button>
              </div>
              <pre class="bg-[#030712] p-2 rounded text-cyan-300 border border-cyan-900/60 font-mono text-[11px] overflow-x-auto">{{ cliCommand }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions Footer -->
      <div class="p-4 border-t border-gray-800 flex items-center justify-between shrink-0 bg-[#070c18]">
        <button
          @click="$emit('open-server', problem.server_id)"
          class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:text-white text-xs font-bold transition cursor-pointer"
          :title="t('pdm_btn_open_workspace_tooltip')"
        >
          {{ t('pdm_btn_open_workspace') }}
        </button>

        <button
          @click="$emit('close')"
          class="px-4 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold transition cursor-pointer"
          :title="t('pdm_btn_close_tooltip')"
        >
          {{ t('pdm_btn_close') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentMessage, formatIncidentRootCause, formatIncidentTip } from '../../utils/formatters'

const { t, locale } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  problem: { type: Object, default: null },
  currentUser: { type: Object, default: null }
})

defineEmits(['close', 'open-server'])

const copied = ref(false)

const sevBadgeClass = computed(() => {
  const s = (props.problem?.severity || '').toLowerCase()
  if (s === 'danger') return 'bg-rose-950 text-rose-300 border border-rose-800'
  if (s === 'critical' || s === 'average') return 'bg-orange-950 text-orange-300 border border-orange-800'
  if (s === 'warning') return 'bg-amber-950 text-amber-300 border border-amber-800'
  return 'bg-cyan-950 text-cyan-300 border border-cyan-800'
})

const rootCauseText = computed(() => formatIncidentRootCause(props.problem))

const impactText = computed(() => {
  const k = props.problem?.key || ''
  if (k.startsWith('ssh_active_session:')) return 'Risk of unauthorized access if origin IP is unrecognized.'
  if (k.startsWith('service_down:')) return 'Associated services or socket ports are unavailable to clients.'
  if (k.includes('disk')) return 'Full storage volumes lead to write failures and crash events.'
  return 'May cause performance degradation and infrastructure instability if unmitigated.'
})

const recommendationText = computed(() => {
  const k = props.problem?.key || ''
  if (k.startsWith('ssh_active_session:')) return 'Verify origin IP and user. If unapproved, terminate active session immediately.'
  if (k.startsWith('service_down:')) return `Restart unit via: sudo systemctl restart ${k.split(':')[1] || 'service'}`
  return 'Inspect top processes in Workspace Tasks tab to locate offending processes.'
})

const cliCommand = computed(() => {
  const k = props.problem?.key || ''
  if (k.startsWith('ssh_active_session:')) {
    const parts = k.split(':')
    const tty = (parts[2] || 'pts/0').replace('_', '/')
    return `sudo pkill -9 -t ${tty.replace('pts/', 'pts/')}`
  }
  if (k.startsWith('service_down:')) {
    const sName = k.split(':')[1] || 'service'
    return `sudo systemctl restart ${sName} && sudo systemctl status ${sName}`
  }
  if (k.includes('disk')) return 'sudo journalctl --vacuum-size=200M && sudo du -xh --max-depth=2 / | sort -rh | head -15'
  if (k.includes('ram')) return 'sudo ps aux --sort=-%mem | head -10'
  if (k.includes('cpu')) return 'sudo ps aux --sort=-%cpu | head -10'
  return ''
})

function copyCli() {
  if (!cliCommand.value) return
  navigator.clipboard.writeText(cliCommand.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}
</script>