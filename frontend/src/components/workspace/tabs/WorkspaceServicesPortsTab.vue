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
                <button
                  @click="$emit('restart-service', svc.name || svc.unit)"
                  class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-600/50 hover:bg-cyan-700 hover:text-white transition cursor-pointer text-xs font-bold inline-flex items-center gap-1.5"
                  :title="`Restart ${svc.name || svc.unit} systemd service`"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                    <path d="M3 3v5h5"/>
                    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                    <path d="M16 21h5v-5"/>
                  </svg>
                  <span>{{ t('ws_act_restart') }}</span>
                </button>
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
              <td class="py-2.5 px-3 text-gray-200">{{ pt.process || pt.service || '-' }}</td>
              <td class="py-2.5 px-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-bold uppercase"
                  :class="(pt.bind || '').includes('127.0.0.1') ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-amber-950 text-amber-300 border border-amber-800 radar-warning'"
                >
                  {{ (pt.bind || '').includes('127.0.0.1') ? 'Local' : 'Public' }}
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
import { ref, computed } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  services: { type: Array, default: () => [] },
  ports: { type: Array, default: () => [] }
})

defineEmits(['restart-service'])

const mode = ref('services')
const search = ref('')

const filteredServices = computed(() => {
  if (!search.value) return props.services
  const q = search.value.toLowerCase()
  return props.services.filter(s =>
    (s.name || s.unit || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q)
  )
})
</script>
