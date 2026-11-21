<template>
  <div class="space-y-4">
    <!-- TOOLBAR ATAS (Search, Filter, Groups) -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 hud-card p-3.5 px-4 rounded-xl">
      <div>
        <h2 class="text-base font-bold text-gray-100 uppercase tracking-wide flex items-center gap-2">
          <span>📡</span>
          <span>{{ t('fleet_title') }}</span>
          <span class="text-xs text-blue-400 font-semibold">({{ filteredServers.length }} {{ t('nodes_monitored') }})</span>
        </h2>
        <p class="text-xs text-gray-400 mt-0.5">
          {{ t('fleet_subtitle') }}
        </p>
      </div>

      <!-- Search & Filters -->
      <div class="flex items-center gap-2.5 flex-wrap">
        <!-- Quick Status Pills -->
        <div class="flex items-center bg-[#090d16] border border-gray-800 rounded-lg p-0.5 text-xs">
          <button
            @click="statusFilter = 'all'"
            :class="[
              'px-3 py-1.5 rounded-md transition cursor-pointer font-semibold',
              statusFilter === 'all' ? 'bg-blue-600 text-white font-bold' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            {{ t('all_statuses') }}
          </button>
          <button
            @click="statusFilter = 'online'"
            :class="[
              'px-3 py-1.5 rounded-md transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'online' ? 'bg-emerald-600 text-white font-bold' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            {{ t('online') }}
          </button>
          <button
            @click="statusFilter = 'offline'"
            :class="[
              'px-3 py-1.5 rounded-md transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'offline' ? 'bg-rose-600 text-white font-bold' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-2 h-2 rounded-full bg-rose-400"></span>
            {{ t('offline') }}
          </button>
        </div>

        <!-- Search Input -->
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search_placeholder')"
            class="bg-[#090d16] border border-gray-800 focus:border-blue-500 rounded-lg px-3.5 py-1.5 text-xs text-gray-100 placeholder-gray-500 w-64 focus:outline-none transition"
          />
          <span class="absolute right-3 top-2 text-xs text-gray-500 pointer-events-none">🔍</span>
        </div>
      </div>
    </div>

    <!-- HIGH-DENSITY FLEET INVENTORY TABLE (Replikasi servers.html Lama + Aksi ala Pantau) -->
    <div class="hud-card rounded-xl overflow-hidden shadow-2xl">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm border-collapse">
          <thead>
            <tr class="bg-[#0e1626] border-b border-gray-800 text-xs uppercase font-bold text-gray-400 tracking-wider select-none">
              <th class="py-2.5 px-3 w-16 text-center">{{ t('col_status') }}</th>
              <th class="py-2.5 px-4 min-w-[180px]">{{ t('col_server') }}</th>
              <th class="py-2.5 px-3 min-w-[130px]">{{ t('col_ip') }}</th>
              <th class="py-2.5 px-3 min-w-[110px]">{{ t('col_platform') }}</th>
              <th class="py-2.5 px-3 min-w-[130px]">{{ t('col_os') }}</th>
              <th class="py-2.5 px-3 min-w-[120px]">{{ t('col_cpu') }}</th>
              <th class="py-2.5 px-3 min-w-[130px]">{{ t('col_memory') }}</th>
              <th class="py-2.5 px-3 min-w-[100px]">{{ t('col_storage') }}</th>
              <th class="py-2.5 px-3 min-w-[90px]">{{ t('col_uptime') }}</th>
              <th class="py-2.5 px-3 min-w-[95px] text-center">{{ t('col_agent') }}</th>
              <th class="py-2.5 px-3 min-w-[105px]">{{ t('col_last_seen') }}</th>
              <th class="py-2.5 px-4 text-right min-w-[180px]">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 bg-[#090d16]/70">
            <tr
              v-for="s in filteredServers"
              :key="s.id"
              class="hover:bg-[#121c30] transition-colors group"
            >
              <!-- 1. STATUS -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="s.is_online"
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-bold font-mono bg-emerald-950/70 text-emerald-400 border border-emerald-800/50 cursor-help"
                  v-tooltip="t('tooltip_node_online')"
                >
                  <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
                  LIVE
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-bold font-mono bg-rose-950/70 text-rose-400 border border-rose-800/50 cursor-help"
                  v-tooltip="t('tooltip_node_offline')"
                >
                  <span class="w-2 h-2 rounded-full bg-rose-500"></span>
                  DOWN
                </span>
              </td>

              <!-- 2. SERVER (Hostname, Group, Tier) -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-1.5">
                  <span class="font-bold text-gray-100 group-hover:text-blue-400 transition text-sm">
                    {{ s.hostname }}
                  </span>
                  <span
                    v-if="s.tier === 1"
                    class="text-xs px-1.5 py-0.2 rounded font-bold bg-blue-950 text-blue-300 border border-blue-800/50"
                  >
                    T1
                  </span>
                  <span
                    v-else
                    class="text-xs px-1.5 py-0.2 rounded font-bold bg-purple-950 text-purple-300 border border-purple-800/50"
                  >
                    T2
                  </span>
                </div>
                <div class="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
                  <span>📁 {{ s.group_name || 'Default' }}</span>
                  <span v-if="s.active_problems_count > 0" class="text-amber-400 font-bold ml-1 font-mono">
                    ● {{ s.active_problems_count }} alert
                  </span>
                </div>
              </td>

              <!-- 3. IP / IFACE -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div
                  class="text-cyan-300 font-semibold font-mono text-sm cursor-help hover:text-cyan-200"
                  v-tooltip="s.ip_address || '127.0.0.1'"
                >
                  {{ s.ip_address || '-' }}
                </div>
                <div class="text-xs text-gray-500 font-mono">ens18 · MTU 1500</div>
              </td>

              <!-- 4. PLATFORM -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-200 text-xs">
                <div
                  class="cursor-help"
                  v-tooltip="`${s.platform || 'KVM Virtual Machine'} (${s.arch || 'x86_64'})`"
                >
                  <div>{{ s.platform || 'KVM Virtual' }}</div>
                  <div class="text-gray-500 font-mono">{{ s.arch || 'x86_64' }}</div>
                </div>
              </td>

              <!-- 5. OS & KERNEL -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-200 text-xs">
                <div class="text-gray-200 font-medium">{{ s.os_label || 'Linux' }}</div>
                <div
                  class="text-gray-500 font-mono truncate max-w-[130px] cursor-help hover:text-cyan-300 transition"
                  v-tooltip="s.kernel || 'Kernel 6.1.x'"
                >
                  {{ s.kernel || 'Kernel 6.1.x' }}
                </div>
              </td>

              <!-- 6. CPU & LOAD -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs font-mono mb-1">
                  <span :class="s.cpu > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.cpu || 0).toFixed(1) }}%</span>
                  <span class="text-gray-500">L {{ (s.load1 || 0).toFixed(2) }}</span>
                </div>
                <div class="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="s.cpu > 80 ? 'bg-rose-500' : s.cpu > 60 ? 'bg-amber-400' : 'bg-blue-500'"
                    :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 7. MEMORY (RAM & SWAP) -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs font-mono mb-1">
                  <span :class="s.mem_pct > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
                  <span class="text-gray-400">{{ formatBytes(s.mem_used) }}</span>
                </div>
                <div class="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all"
                    :class="s.mem_pct > 80 ? 'bg-rose-500' : s.mem_pct > 60 ? 'bg-amber-400' : 'bg-emerald-500'"
                    :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 8. STORAGE -->
              <td class="py-2.5 px-3 whitespace-nowrap">
                <div class="text-xs text-gray-300 font-mono mb-1">
                  <span :class="(s.disk_pct || 35) > 85 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">
                    {{ s.disk_pct || 35 }}%
                  </span>
                  <span class="text-gray-500 ml-1">/root</span>
                </div>
                <div class="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    class="h-full bg-cyan-500 rounded-full"
                    :style="{ width: `${s.disk_pct || 35}%` }"
                  ></div>
                </div>
              </td>

              <!-- 9. UPTIME -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-300 text-xs font-mono">
                {{ formatUptime(s.uptime_secs) }}
              </td>

              <!-- 10. AGENT & PACKAGES -->
              <td class="py-2.5 px-3 whitespace-nowrap text-center">
                <span class="px-2 py-0.5 rounded text-xs bg-gray-800/90 text-gray-300 border border-gray-700/60 font-mono font-medium">
                  v{{ s.agent_version || '0.1.0' }}
                </span>
                <span
                  v-if="s.apt_upgradable > 0"
                  class="ml-1 px-1.5 py-0.5 rounded text-xs font-bold bg-amber-950 text-amber-300 border border-amber-800 font-mono cursor-help"
                  v-tooltip="`${s.apt_upgradable} ${t('tooltip_apt_upgradable')}`"
                >
                  {{ s.apt_upgradable }}
                </span>
              </td>

              <!-- 11. LAST SEEN -->
              <td class="py-2.5 px-3 whitespace-nowrap text-gray-400 text-xs font-mono">
                <div>{{ formatRelativeTime(s.last_seen) }}</div>
                <div class="text-emerald-400/90 font-semibold">12ms latency</div>
              </td>

              <!-- 12. KLASTER TOMBOL AKSI (POLA APLIKASI PANTAU) -->
              <td class="py-2.5 px-4 whitespace-nowrap text-right">
                <div class="inline-flex items-center gap-1.5">
                  <!-- Tombol VIEW (Membuka Jendela Kontrol Mengambang) -->
                  <button
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs shadow transition cursor-pointer flex items-center gap-1.5"
                    v-tooltip="t('btn_view')"
                  >
                    <span>📂</span>
                    <span>{{ t('btn_view') }}</span>
                  </button>

                  <!-- Tombol Shortcut METRIKS -->
                  <button
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="w-7 h-7 flex items-center justify-center rounded-md bg-[#131d33] hover:bg-blue-600/30 text-blue-400 border border-gray-700/80 transition cursor-pointer text-xs"
                    v-tooltip="t('tooltip_metrics')"
                  >
                    📊
                  </button>

                  <!-- Tombol Shortcut TERMINAL WEB -->
                  <button
                    @click="$emit('open-workspace', s.id, 'terminal')"
                    class="w-7 h-7 flex items-center justify-center rounded-md bg-[#131d33] hover:bg-blue-600/30 text-blue-400 border border-gray-700/80 transition cursor-pointer text-xs"
                    v-tooltip="t('tooltip_terminal')"
                  >
                    🖥️
                  </button>

                  <!-- Tombol SYNC / PROBE INSTAN -->
                  <button
                    @click="$emit('probe-node', s.id)"
                    class="w-7 h-7 flex items-center justify-center rounded-md bg-[#131d33] hover:bg-emerald-600/30 text-gray-300 hover:text-emerald-400 border border-gray-700/80 transition cursor-pointer text-xs"
                    v-tooltip="t('tooltip_sync')"
                  >
                    🔄
                  </button>

                  <!-- Menu DROPDOWN ⋮ (Aksi Tambahan) -->
                  <button
                    @click="$emit('more-actions', s.id, $event)"
                    class="w-7 h-7 flex items-center justify-center rounded-md bg-[#131d33] hover:bg-gray-700 text-gray-400 hover:text-white border border-gray-700/80 transition cursor-pointer text-xs font-bold"
                    v-tooltip="t('btn_more')"
                  >
                    ⋮
                  </button>
                </div>
              </td>
            </tr>

            <!-- EMPTY STATE ROW (Kondisi Bersih Awal) -->
            <tr v-if="filteredServers.length === 0">
              <td colspan="12" class="py-12 px-4 text-center">
                <div class="flex flex-col items-center justify-center gap-2">
                  <span class="text-3xl text-gray-600">📡</span>
                  <div class="text-sm font-bold text-gray-200 font-mono tracking-wide">{{ t('fleet_empty_title') }}</div>
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
  return `${h}h ${m}m`
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
