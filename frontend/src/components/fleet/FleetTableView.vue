<template>
  <div class="space-y-4">
    <!-- TOOLBAR ATAS (Search, Filter, Groups) -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// RECON: FLEET TELEMETRY MATRIX</span>
          <span class="text-xs text-cyan-400 font-bold">({{ filteredServers.length }} {{ t('nodes_monitored') }})</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('fleet_subtitle') }}
        </p>
      </div>

      <!-- Search & Filters -->
      <div class="flex items-center gap-2.5 flex-wrap font-mono">
        <!-- Quick Status Pills -->
        <div class="flex items-center bg-[#060a14] border border-cyan-900/40 rounded p-0.5 text-xs">
          <button
            @click="statusFilter = 'all'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer font-semibold',
              statusFilter === 'all' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            {{ t('all_statuses') }}
          </button>
          <button
            @click="statusFilter = 'online'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'online' ? 'bg-emerald-950 text-emerald-300 font-bold border border-emerald-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
            {{ t('online') }}
          </button>
          <button
            @click="statusFilter = 'offline'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'offline' ? 'bg-rose-950 text-rose-300 font-bold border border-rose-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            {{ t('offline') }}
          </button>
        </div>

        <!-- Search Input -->
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search_placeholder')"
            class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 rounded px-3 py-1 text-xs text-gray-100 placeholder-gray-500 w-64 focus:outline-none transition font-mono"
          />
          <span class="absolute right-2.5 top-1.5 text-xs text-gray-500 pointer-events-none">🔍</span>
        </div>
      </div>
    </div>

    <!-- HIGH-DENSITY FLEET TELEMETRY MATRIX TABLE -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider select-none">
              <th class="py-2.5 px-3 w-16 text-center">{{ t('col_status') }}</th>
              <th class="py-2.5 px-4 min-w-[180px]">{{ t('col_server') }}</th>
              <th class="py-2.5 px-3 min-w-[130px]">{{ t('col_ip') }}</th>
              <th class="py-2.5 px-3 min-w-[110px]">{{ t('col_platform') }}</th>
              <th class="py-2.5 px-3 min-w-[130px]">{{ t('col_os') }}</th>
              <th class="py-2.5 px-3 min-w-[125px]">{{ t('col_cpu') }}</th>
              <th class="py-2.5 px-3 min-w-[135px]">{{ t('col_memory') }}</th>
              <th class="py-2.5 px-3 min-w-[105px]">{{ t('col_storage') }}</th>
              <th class="py-2.5 px-3 min-w-[90px]">{{ t('col_uptime') }}</th>
              <th class="py-2.5 px-3 min-w-[95px] text-center">{{ t('col_agent') }}</th>
              <th class="py-2.5 px-3 min-w-[105px]">{{ t('col_last_seen') }}</th>
              <th class="py-2.5 px-4 text-right min-w-[200px]">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="s in filteredServers"
              :key="s.id"
              class="hover:bg-cyan-950/20 transition-colors group"
            >
              <!-- 1. STATUS -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="s.is_online"
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60"
                  :title="t('tooltip_node_online')"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
                  LIVE
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-700/60"
                  :title="t('tooltip_node_offline')"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                  DOWN
                </span>
              </td>

              <!-- 2. SERVER (Hostname, Group, Tier) -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-1.5">
                  <span class="font-bold text-gray-100 group-hover:text-cyan-300 transition text-sm">
                    {{ s.hostname }}
                  </span>
                  <span
                    v-if="s.tier === 1"
                    class="text-[10px] px-1.5 py-0.2 rounded font-bold bg-cyan-950 text-cyan-300 border border-cyan-800"
                  >
                    T1
                  </span>
                  <span
                    v-else
                    class="text-[10px] px-1.5 py-0.2 rounded font-bold bg-purple-950 text-purple-300 border border-purple-800"
                  >
                    T2
                  </span>
                </div>
                <div class="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                  <span>📁 {{ s.group_name || 'DEFAULT' }}</span>
                  <span v-if="s.active_problems_count > 0" class="text-amber-400 font-bold ml-1 radar-warning px-1 rounded">
                    ● {{ s.active_problems_count }} alert
                  </span>
                </div>
              </td>

              <!-- 3. IP / IFACE -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div
                  class="text-cyan-300 font-semibold text-xs cursor-help hover:text-cyan-200"
                  :title="s.ip_address || '127.0.0.1'"
                >
                  {{ s.ip_address || '-' }}
                </div>
                <div class="text-[11px] text-gray-500 font-mono">ens18 · MTU 1500</div>
              </td>

              <!-- 4. PLATFORM -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-300 text-xs">
                <div
                  class="cursor-help"
                  :title="`${s.platform || 'KVM Virtual Machine'} (${s.arch || 'x86_64'})`"
                >
                  <div>{{ s.platform || 'KVM Virtual' }}</div>
                  <div class="text-gray-500 text-[11px]">{{ s.arch || 'x86_64' }}</div>
                </div>
              </td>

              <!-- 5. OS & KERNEL -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-300 text-xs">
                <div class="text-gray-200 font-medium">{{ s.os_label || 'Linux' }}</div>
                <div
                  class="text-gray-500 text-[11px] truncate max-w-[130px] cursor-help hover:text-cyan-300 transition"
                  :title="s.kernel || 'Kernel 6.1.x'"
                >
                  {{ s.kernel || 'Kernel 6.1.x' }}
                </div>
              </td>

              <!-- 6. CPU & LOAD -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs mb-1">
                  <span :class="s.cpu > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.cpu || 0).toFixed(1) }}%</span>
                  <span class="text-gray-500 text-[11px]">L {{ (s.load1 || 0).toFixed(2) }}</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.cpu > 80 ? 'cyber-bar-fill-crimson' : s.cpu > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-cyan'"
                    :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 7. MEMORY (RAM & SWAP) -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs mb-1">
                  <span :class="s.mem_pct > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
                  <span class="text-gray-400 text-[11px]">{{ formatBytes(s.mem_used) }}</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.mem_pct > 80 ? 'cyber-bar-fill-crimson' : s.mem_pct > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-emerald'"
                    :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 8. STORAGE -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="text-xs text-gray-300 mb-1">
                  <span :class="(s.disk_pct || 35) > 85 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">
                    {{ s.disk_pct || 35 }}%
                  </span>
                  <span class="text-gray-500 ml-1 text-[11px]">/root</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    class="cyber-bar-fill-cyan"
                    :style="{ width: `${s.disk_pct || 35}%` }"
                  ></div>
                </div>
              </td>

              <!-- 9. UPTIME -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-300 text-xs">
                {{ formatUptime(s.uptime_secs) }}
              </td>

              <!-- 10. AGENT & PACKAGES -->
              <td class="py-2.5 px-3 whitespace-nowrap text-center">
                <span class="px-2 py-0.5 rounded text-[11px] bg-gray-900 text-gray-300 border border-gray-700/80 font-bold">
                  v{{ s.agent_version || '0.1.0' }}
                </span>
                <span
                  v-if="s.apt_upgradable > 0"
                  class="ml-1 px-1.5 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 cursor-help"
                  :title="`${s.apt_upgradable} ${t('tooltip_apt_upgradable')}`"
                >
                  {{ s.apt_upgradable }}
                </span>
              </td>

              <!-- 11. LAST SEEN & PING -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-400 text-xs">
                <div>{{ formatRelativeTime(s.last_seen) }}</div>
                <div class="text-emerald-400/90 font-semibold text-[11px]">● 12ms ping</div>
              </td>

              <!-- 12. KLASTER TOMBOL TINDAKAN (TACTICAL COMMAND CONTROLLER) -->
              <td class="py-2.5 px-4 whitespace-nowrap text-right">
                <div class="inline-flex items-center gap-1.5">
                  <!-- Tombol INVESTIGATE (Membuka Jendela Kontrol Taktis Mengambang) -->
                  <button
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-700 text-cyan-300 hover:text-white border border-cyan-500/50 text-xs font-bold shadow-[0_0_8px_rgba(56,189,248,0.2)] transition cursor-pointer flex items-center gap-1.5"
                    :title="t('tooltip_view')"
                  >
                    <span>⚡</span>
                    <span>INVESTIGATE</span>
                  </button>

                  <!-- Shortcut METRIKS -->
                  <button
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="w-7 h-7 flex items-center justify-center rounded bg-[#0b1324] hover:bg-cyan-950 text-cyan-400 border border-cyan-800/40 transition cursor-pointer text-xs"
                    :title="t('tooltip_metrics')"
                  >
                    📊
                  </button>

                  <!-- Shortcut TERMINAL TTY -->
                  <button
                    @click="$emit('open-workspace', s.id, 'terminal')"
                    class="w-7 h-7 flex items-center justify-center rounded bg-[#0b1324] hover:bg-cyan-950 text-cyan-400 border border-cyan-800/40 transition cursor-pointer text-xs"
                    :title="t('tooltip_terminal')"
                  >
                    🖥️
                  </button>

                  <!-- Shortcut PROBE INSTAN -->
                  <button
                    @click="$emit('probe-node', s.id)"
                    class="w-7 h-7 flex items-center justify-center rounded bg-[#0b1324] hover:bg-emerald-950 text-emerald-400 border border-cyan-800/40 transition cursor-pointer text-xs"
                    :title="t('tooltip_sync')"
                  >
                    🔄
                  </button>

                  <!-- Menu DROPDOWN ⋮ -->
                  <button
                    @click="$emit('more-actions', s.id, $event)"
                    class="w-7 h-7 flex items-center justify-center rounded bg-[#0b1324] hover:bg-gray-800 text-gray-400 hover:text-white border border-gray-700/80 transition cursor-pointer text-xs font-bold"
                    :title="t('btn_more')"
                  >
                    ⋮
                  </button>
                </div>
              </td>
            </tr>

            <!-- EMPTY STATE ROW (Kondisi Bersih Awal) -->
            <tr v-if="filteredServers.length === 0">
              <td colspan="12" class="py-14 px-4 text-center">
                <div class="flex flex-col items-center justify-center gap-2">
                  <span class="text-3xl text-gray-600">📡</span>
                  <div class="text-sm font-bold text-gray-200 font-mono tracking-wider uppercase">// {{ t('fleet_empty_title') }}</div>
                  <div class="text-xs text-gray-400 font-mono max-w-md">{{ t('fleet_empty_desc') }}</div>
                </div>
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
import { useI18n } from '../../i18n'

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  }
})

defineEmits(['open-workspace', 'probe-node', 'more-actions'])

const { t } = useI18n()

const searchQuery = ref('')
const statusFilter = ref('all') // all, online, offline

const filteredServers = computed(() => {
  let list = props.servers || []
  if (statusFilter.value === 'online') {
    list = list.filter(s => s.is_online)
  } else if (statusFilter.value === 'offline') {
    list = list.filter(s => !s.is_online)
  }

  if (!searchQuery.value.trim()) return list
  const q = searchQuery.value.toLowerCase()
  return list.filter(s =>
    (s.hostname || '').toLowerCase().includes(q) ||
    (s.ip_address || '').includes(q) ||
    (s.group_name || '').toLowerCase().includes(q) ||
    (s.os_label || '').toLowerCase().includes(q)
  )
})

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatUptime(secs) {
  if (!secs) return '-'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatRelativeTime(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return '-'
  const diffSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (diffSec < 10) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const min = Math.floor(diffSec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}
</script>
