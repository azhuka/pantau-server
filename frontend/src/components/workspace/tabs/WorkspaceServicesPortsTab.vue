<template>
  <div class="space-y-4 font-mono">
    <!-- Sub-Toggle Switcher -->
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-xs">
        <button
          @click="mode = 'services'"
          class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
          :class="mode === 'services' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span>Systemd Services ({{ filteredServices.length }})</span>
        </button>
        <button
          @click="mode = 'ports'"
          class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
          :class="mode === 'ports' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <span>Listening Ports ({{ (ports || []).length }})</span>
        </button>
      </div>

      <!-- Search Filter Input -->
      <input
        v-if="mode === 'services'"
        v-model="search"
        type="text"
        :placeholder="t('ws_services_search')"
        class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 text-gray-200 text-xs rounded px-3 py-1.5 w-60 focus:outline-none"
      />
    </div>

    <!-- View A: Systemd Services Table -->
    <div v-if="mode === 'services'" class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="overflow-x-auto max-h-[520px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
            <tr class="text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('ws_col_service_name') }}</th>
              <th class="py-2.5 px-3">{{ t('col_status') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_description') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(svc, idx) in filteredServices" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 px-3 font-semibold text-gray-200">{{ svc.name || svc.unit }}</td>
              <td class="py-2.5 px-3">
                <span
                  class="px-2 py-0.5 rounded text-[11px] uppercase font-bold"
                  :class="svc.active === 'active' || svc.sub === 'running' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60' : 'bg-gray-800 text-gray-400'"
                >
                  {{ svc.sub || svc.active || 'unknown' }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-400 truncate max-w-xs">{{ svc.description || '-' }}</td>
              <td class="py-2.5 px-3 text-right">
                <div class="relative inline-block text-left">
                  <button
                    type="button"
                    @click.stop="toggleSvcDropdown(svc.name || svc.unit)"
                    class="p-1.5 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 transition cursor-pointer flex items-center justify-center shadow-sm"
                    :title="t('col_actions')"
                  >
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="1.5"></circle>
                      <circle cx="12" cy="5" r="1.5"></circle>
                      <circle cx="12" cy="19" r="1.5"></circle>
                    </svg>
                  </button>

                  <div
                    v-if="openSvcId === (svc.name || svc.unit)"
                    @click.stop
                    class="absolute right-0 mt-1 w-36 rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-50 py-1 font-mono text-xs divide-y divide-gray-800"
                  >
                    <div class="py-0.5">
                      <!-- Restart Service -->
                      <button
                        type="button"
                        @click="handleAction('restart_service', svc.name || svc.unit)"
                        class="w-full px-3 py-1.5 text-left text-cyan-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition font-bold"
                      >
                        <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
                        <span>Restart</span>
                      </button>

                      <!-- Start Service (if not running) -->
                      <button
                        v-if="svc.active !== 'active' && svc.sub !== 'running'"
                        type="button"
                        @click="handleAction('start_service', svc.name || svc.unit)"
                        class="w-full px-3 py-1.5 text-left text-emerald-300 hover:text-white hover:bg-emerald-950/80 flex items-center gap-2 cursor-pointer transition font-bold"
                      >
                        <svg class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        <span>Start</span>
                      </button>

                      <!-- Reload Service (if running) -->
                      <button
                        v-if="svc.active === 'active' || svc.sub === 'running'"
                        type="button"
                        @click="handleAction('reload_service', svc.name || svc.unit)"
                        class="w-full px-3 py-1.5 text-left text-amber-300 hover:text-white hover:bg-amber-950/80 flex items-center gap-2 cursor-pointer transition"
                      >
                        <svg class="w-3.5 h-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                        <span>Reload</span>
                      </button>
                    </div>

                    <div class="py-0.5">
                      <!-- Stop Service -->
                      <button
                        type="button"
                        :disabled="isProtectedService(svc.name || svc.unit)"
                        @click="handleAction('stop_service', svc.name || svc.unit)"
                        class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 flex items-center gap-2 transition disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                        :title="isProtectedService(svc.name || svc.unit) ? 'Critical service is protected by guardrails' : 'Stop systemd service unit'"
                      >
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg>
                        <span>Stop</span>
                      </button>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- View B: Listening Ports & Sockets Table -->
    <div v-else class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="overflow-x-auto max-h-[520px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
            <tr class="text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('ws_col_port') || 'Port' }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_proto') || 'Proto' }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_bind') }}</th>
              <th class="py-2.5 px-3">{{ t('ws_col_service') }}</th>
              <th class="py-2.5 px-3 text-center">{{ t('ws_col_class') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(pt, idx) in ports || []" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 px-3 font-bold text-cyan-300">{{ pt.port }}</td>
              <td class="py-2.5 px-3 text-gray-400 uppercase">{{ pt.proto || 'tcp' }}</td>
              <td class="py-2.5 px-3 text-gray-300 font-semibold">{{ pt.bind || pt.address || '0.0.0.0' }}</td>
              <td class="py-2.5 px-3 text-gray-200">{{ pt.service || pt.program || pt.process || '-' }}</td>
              <td class="py-2.5 px-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-[10px] font-bold"
                  :class="pt.bind === '127.0.0.1' || pt.bind === '::1' ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-amber-950 text-amber-300 border border-amber-800'"
                >
                  {{ pt.bind === '127.0.0.1' || pt.bind === '::1' ? 'INTERNAL' : 'PUBLIC' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  services: { type: Array, default: () => [] },
  ports: { type: Array, default: () => [] },
})

const emit = defineEmits(['restart-service', 'service-action'])

const mode = ref('services')
const search = ref('')
const openSvcId = ref(null)

function toggleSvcDropdown(id) {
  openSvcId.value = openSvcId.value === id ? null : id
}

function closeDropdowns() {
  openSvcId.value = null
}

onMounted(() => {
  window.addEventListener('click', closeDropdowns)
})

onUnmounted(() => {
  window.removeEventListener('click', closeDropdowns)
})

function isProtectedService(name) {
  const n = (name || '').toLowerCase()
  return ['agent_pantau', 'agent-pantau', 'sshd', 'ssh', 'systemd', 'pantau-server'].some(cs => n.includes(cs))
}

function handleAction(action, unit) {
  openSvcId.value = null
  if (action === 'restart_service') {
    emit('restart-service', unit)
  }
  emit('service-action', { action, unit })
}

const filteredServices = computed(() => {
  if (!search.value) return props.services
  const q = search.value.toLowerCase()
  return props.services.filter(s =>
    (s.name || s.unit || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})
</script>
