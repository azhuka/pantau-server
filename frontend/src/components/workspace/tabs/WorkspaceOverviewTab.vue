<template>
  <div class="space-y-4 font-mono">
    <!-- Grid Atas: Metrik Chips Real-Time -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
      <!-- CPU Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// CPU</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">
          {{ (server?.metrics?.cpu || 0).toFixed(1) }}%
        </div>
        <div class="cyber-bar-track mt-1.5">
          <div
            :class="(server?.metrics?.cpu || 0) > 80 ? 'cyber-bar-fill-crimson' : (server?.metrics?.cpu || 0) > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-cyan'"
            :style="{ width: `${Math.min(server?.metrics?.cpu || 0, 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Load Avg Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// LOAD AVG</div>
        <div class="text-sm font-bold text-cyan-300 mt-1 truncate">
          {{ (server?.metrics?.load || [0, 0, 0]).map(v => Number(v).toFixed(2)).join(' · ') }}
        </div>
        <div class="text-[10px] text-gray-500 mt-1">1 / 5 / 15m</div>
      </div>

      <!-- RAM Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// RAM</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">
          {{ formatBytes(server?.metrics?.mem_used) }}
        </div>
        <div class="cyber-bar-track mt-1.5">
          <div
            class="cyber-bar-fill-emerald"
            :style="{ width: `${Math.min(((server?.metrics?.mem_used || 0) / (server?.metrics?.mem_total || 1)) * 100, 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Swap Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// SWAP</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">
          {{ formatBytes(server?.metrics?.swap_used) }}
        </div>
        <div class="cyber-bar-track mt-1.5">
          <div
            class="cyber-bar-fill-cyan"
            :style="{ width: `${Math.min(((server?.metrics?.swap_used || 0) / (server?.metrics?.swap_total || 1)) * 100, 100)}%` }"
          ></div>
        </div>
      </div>

      <!-- Processes Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// PROCESSES</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">
          {{ server?.metrics?.procs || processesCount || 0 }}
        </div>
        <div class="text-[10px] text-gray-500 mt-1">tasks running</div>
      </div>

      <!-- Uptime Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// UPTIME</div>
        <div class="text-sm font-bold text-emerald-400 mt-1 truncate">
          {{ formatUptime(server?.metrics?.uptime_secs) }}
        </div>
        <div class="text-[10px] text-gray-500 mt-1 truncate">{{ server?.os_label || 'Linux' }}</div>
      </div>
    </div>

    <!-- Hardware Specs & Catatan Server Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
      <!-- Hardware Specs Card -->
      <div class="hud-tactical-card rounded-xl p-4">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-2.5">
          // {{ t('ws_hw_specs') }}
        </h3>
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div>
            <span class="text-gray-500">{{ t('ws_cpu_model') }}</span>
            <div class="text-gray-200 truncate mt-0.5 font-bold">{{ server?.hardware?.cpu_model || '-' }}</div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('ws_core_capacity') }}</span>
            <div class="text-gray-200 mt-0.5 font-bold">{{ server?.hardware?.cores || 1 }} Core(s)</div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('ws_arch') }}</span>
            <div class="text-gray-200 mt-0.5 font-bold">{{ server?.arch || 'x86_64' }}</div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('ws_asset_group') }}</span>
            <div class="text-cyan-400 mt-0.5 font-bold">{{ server?.group_name }} (Tier {{ server?.tier }})</div>
          </div>
        </div>
      </div>

      <!-- Catatan Server (Notes Card) -->
      <div class="hud-tactical-card rounded-xl p-4 flex flex-col justify-between">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>
        <div>
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xs font-bold text-purple-400 uppercase tracking-wider">
              // HOST DESCRIPTION &amp; NOTES
            </h3>
            <span class="text-[10px] text-gray-500">OPERATOR MEMO</span>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed">
            {{ server?.notes || 'No operational notes attached to this host yet. Notes can be configured in Host Settings.' }}
          </p>
        </div>
        <div class="mt-3 pt-2 border-t border-cyan-500/10 flex items-center justify-between text-[11px] text-gray-500">
          <span>TAGS: {{ server?.tags || 'core, production' }}</span>
          <span class="text-cyan-400 font-semibold">{{ server?.is_isolated_net ? 'Isolated Network' : 'Standard Network' }}</span>
        </div>
      </div>
    </div>

    <!-- Partisi Penyimpanan (Disks Table) -->
    <div class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">
        // {{ t('ws_disk_partitions') }}
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
              <th class="pb-2">{{ t('ws_col_mount') || 'Mount Point' }}</th>
              <th class="pb-2">{{ t('ws_col_fs') || 'Filesystem' }}</th>
              <th class="pb-2">{{ t('dash_kpi_total') }}</th>
              <th class="pb-2">{{ t('ws_col_used') || 'Used' }}</th>
              <th class="pb-2">{{ t('ws_col_avail') || 'Avail' }}</th>
              <th class="pb-2 min-w-[140px]">{{ t('col_util_pct') || 'Util (%)' }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(d, idx) in server?.metrics?.disks || []" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 text-cyan-300 font-semibold">{{ d.mount || d.mounted_on || '/' }}</td>
              <td class="py-2.5 text-gray-400">{{ d.filesystem || d.device || '-' }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.total_bytes || d.total) }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.used_bytes || d.used) }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.free_bytes || d.free || d.avail) }}</td>
              <td class="py-2.5">
                <div class="flex items-center gap-2">
                  <span :class="(d.used_percent || d.percent || d.pct || 0) > 85 ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'">
                    {{ (d.used_percent || d.percent || d.pct || 0).toFixed(1) }}%
                  </span>
                  <div class="cyber-bar-track flex-1">
                    <div
                      :class="(d.used_percent || d.percent || d.pct || 0) > 85 ? 'cyber-bar-fill-crimson' : 'cyber-bar-fill-cyan'"
                      :style="{ width: `${Math.min(d.used_percent || d.percent || d.pct || 0, 100)}%` }"
                    ></div>
                  </div>
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
import { useI18n } from '../../../i18n'
import { formatBytes, formatUptime } from '../../../utils/formatters'

const { t } = useI18n()

defineProps({
  server: { type: Object, default: () => ({}) },
  processesCount: { type: Number, default: 0 }
})
</script>
