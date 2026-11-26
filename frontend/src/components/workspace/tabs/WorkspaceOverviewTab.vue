<template>
  <div class="space-y-4 font-mono">
    <!-- Grid Atas: Metrik Chips Real-Time -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
      <!-- CPU Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">CPU</div>
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
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">LOAD AVG</div>
        <div class="text-sm font-bold text-cyan-300 mt-1 truncate">
          {{ (server?.metrics?.load || [0, 0, 0]).map(v => Number(v).toFixed(2)).join(' · ') }}
        </div>
        <div class="text-[10px] text-gray-500 mt-1">1 / 5 / 15m</div>
      </div>

      <!-- RAM Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">RAM</div>
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
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">SWAP</div>
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
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">PROCESSES</div>
        <div class="text-xl font-black text-gray-100 mt-0.5">
          {{ server?.metrics?.procs || processesCount || 0 }}
        </div>
        <div class="text-[10px] text-gray-500 mt-1">tasks running</div>
      </div>

      <!-- Uptime Chip -->
      <div class="hud-tactical-card p-3 rounded-lg">
        <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">UPTIME</div>
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
          {{ t('ws_hw_specs') }}
        </h3>
        <div class="grid grid-cols-2 gap-3 text-xs">
          <div>
            <span class="text-gray-500">{{ t('ws_cpu_model') }}</span>
            <div class="text-gray-200 truncate mt-0.5 font-bold" :title="server?.hardware?.cpu?.model || server?.hardware?.cpu_model">
              {{ server?.hardware?.cpu?.model || server?.hardware?.cpu_model || '-' }}
            </div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('ws_core_capacity') }}</span>
            <div class="text-gray-200 mt-0.5 font-bold">{{ server?.hardware?.cpu?.cores || server?.hardware?.cores || 1 }} Core(s)</div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('ws_arch') }}</span>
            <div class="text-gray-200 mt-0.5 font-bold">{{ server?.arch || server?.hardware?.cpu?.arch || '-' }}</div>
          </div>
          <div>
            <span class="text-gray-500">{{ t('col_platform') }}</span>
            <div class="text-gray-200 truncate mt-0.5 font-bold" :title="[server?.hardware?.platform?.vendor, server?.hardware?.platform?.product].filter(Boolean).join(' ')">
              {{ server?.hardware?.platform?.platform_label || server?.hardware?.platform?.virt || server?.platform_label || '-' }}
            </div>
          </div>
          <div class="col-span-2">
            <span class="text-gray-500">{{ t('ws_asset_group') }}</span>
            <div class="flex items-center gap-1.5 mt-0.5">
              <span class="text-cyan-400 font-bold">{{ server?.group_name || t('flt_ungrouped') }}</span>
              <span
                v-if="server?.tier === 1"
                class="inline-flex items-center justify-center p-0.5 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-700/50"
                :title="t('env_prod')"
              >
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                  <polyline points="9 12 11 14 15 10"/>
                </svg>
              </span>
              <span
                v-else
                class="inline-flex items-center justify-center p-0.5 rounded bg-slate-900/60 text-slate-400 border border-slate-700/50"
                :title="t('env_non_prod')"
              >
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/>
                  <path d="M8.5 2h7"/>
                  <path d="M7 16h10"/>
                </svg>
              </span>
              <span v-if="server?.hardware?.platform?.product" class="text-gray-500 text-[11px] ml-2 truncate" :title="[server?.hardware?.platform?.vendor, server?.hardware?.platform?.product].filter(Boolean).join(' ')">
                · {{ [server?.hardware?.platform?.vendor, server?.hardware?.platform?.product].filter(Boolean).join(' ') }}
              </span>
            </div>
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
              HOST DESCRIPTION &amp; NOTES
            </h3>
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-gray-500">OPERATOR MEMO</span>
              <button
                v-if="canEditNotes"
                type="button"
                @click="noteModalOpen = true"
                class="inline-flex items-center justify-center rounded border border-purple-700/60 bg-purple-950/50 text-purple-300 hover:bg-purple-900/70 hover:text-white transition cursor-pointer"
                style="width: 26px; height: 26px; min-width: 26px; border-radius: 4px;"
                title="Edit Host Description & Notes"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            </div>
          </div>
          <p class="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">
            {{ server?.notes || 'No operational notes attached to this host yet.' }}
          </p>
        </div>
        <div class="mt-3 pt-2 border-t border-cyan-500/10 flex items-center justify-between text-[11px] text-gray-500">
          <span>TAGS: {{ server?.tags || '-' }}</span>
          <span class="text-cyan-400 font-semibold">{{ server?.is_isolated_net ? 'Isolated Network' : 'Standard Network' }}</span>
        </div>
      </div>
    </div>

    <!-- Performance Metric History (2x2 Grid + Network Throughput) -->
    <WorkspacePerfCharts :server-id="server?.id" />

    <!-- Partisi Penyimpanan (Disks Table) -->
    <div class="hud-tactical-card rounded-xl p-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">
        {{ t('ws_disk_partitions') }}
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
              <th class="pb-2 text-center w-20">{{ t('col_actions') || 'Actions' }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(d, idx) in server?.metrics?.disks || []" :key="idx" class="hover:bg-cyan-950/20">
              <td class="py-2.5 text-cyan-300 font-semibold">{{ d.mount || d.mounted_on || '/' }}</td>
              <td class="py-2.5 text-gray-400">{{ d.type || d.filesystem || d.device || '-' }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.total_bytes || d.total) }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.used_bytes || d.used) }}</td>
              <td class="py-2.5 text-gray-300">{{ formatBytes(d.free_bytes ?? d.free ?? d.avail ?? Math.max((d.total_bytes || d.total || 0) - (d.used_bytes || d.used || 0), 0)) }}</td>
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
              <td class="py-2.5 text-center">
                <button
                  type="button"
                  @click="openStorageAnalysis(d.mount || d.mounted_on || '/')"
                  class="inline-flex items-center justify-center rounded border border-cyan-800/60 bg-cyan-950/50 text-cyan-300 hover:bg-cyan-900/70 hover:text-white transition cursor-pointer"
                  style="width: 26px; height: 26px; min-width: 26px; border-radius: 4px;"
                  :title="`Analyze Storage on ${d.mount || d.mounted_on || '/'}`"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <StorageTriageModal
      :is-open="storageTriageOpen"
      :server-id="server?.id"
      :mount-path="storageTriageMount"
      @close="storageTriageOpen = false"
    />

    <EditNoteModal
      :is-open="noteModalOpen"
      :server="server"
      @close="noteModalOpen = false"
      @updated="onNoteUpdated"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../../i18n'
import { formatBytes, formatUptime } from '../../../utils/formatters'
import { useToast } from '../../../utils/useToast'
import WorkspacePerfCharts from './WorkspacePerfCharts.vue'
import StorageTriageModal from '../StorageTriageModal.vue'
import EditNoteModal from '../../assets/modals/EditNoteModal.vue'

const { t } = useI18n()
const toast = useToast()

defineProps({
  server: { type: Object, default: () => ({}) },
  processesCount: { type: Number, default: 0 },
  canEditNotes: { type: Boolean, default: false },
})

const emit = defineEmits(['note-updated'])

const storageTriageOpen = ref(false)
const storageTriageMount = ref('/')
const noteModalOpen = ref(false)

function openStorageAnalysis(mount) {
  storageTriageMount.value = mount || '/'
  storageTriageOpen.value = true
}

function onNoteUpdated(msg) {
  toast.success(msg || 'Host notes saved')
  emit('note-updated')
}
</script>
