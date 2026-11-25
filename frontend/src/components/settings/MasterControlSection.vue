<template>
  <div class="space-y-6">
    <!-- Flash Banner -->
    <div
      v-if="flashMsg"
      class="p-3 rounded-lg border text-xs font-mono flex items-center justify-between"
      :class="flashType === 'success' ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300' : 'bg-rose-950/60 border-rose-800 text-rose-300'"
    >
      <span>{{ flashMsg }}</span>
      <button @click="flashMsg = ''" class="text-gray-400 hover:text-white font-bold ml-2 cursor-pointer">&times;</button>
    </div>

    <!-- Stat Cards KPI Strip -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
      <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 text-center">
        <div class="text-[10px] text-gray-400 uppercase font-semibold">{{ t('mc_db_size') }}</div>
        <div class="text-lg font-extrabold text-cyan-300 mt-0.5">
          {{ mcStatus?.database?.total_size_mb || '0' }} <span class="text-xs font-normal text-gray-400">MB</span>
        </div>
        <div class="text-[10px] text-gray-400 mt-1">
          {{ mcStatus?.database?.tables?.length || 0 }} {{ t('tbl_registered', 'Tabel') }}
        </div>
      </div>

      <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 text-center">
        <div class="text-[10px] text-gray-400 uppercase font-semibold">{{ t('mc_host_ram') }}</div>
        <div class="text-lg font-extrabold text-emerald-300 mt-0.5">
          {{ formatBytes(mcStatus?.memory?.used) }}
        </div>
        <div class="text-[10px] text-gray-400 mt-1">
          Total: {{ formatBytes(mcStatus?.memory?.total) }} ({{ mcStatus?.memory?.percent || 0 }}%)
        </div>
      </div>

      <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 text-center">
        <div class="text-[10px] text-gray-400 uppercase font-semibold">{{ t('mc_host_cpu') }}</div>
        <div class="text-lg font-extrabold text-amber-300 mt-0.5">
          {{ mcStatus?.cpu?.cpu_percent != null ? mcStatus.cpu.cpu_percent + '%' : 'N/A' }}
        </div>
        <div class="text-[10px] text-gray-400 mt-1">
          {{ mcStatus?.cpu?.cores || 1 }} Cores Online
        </div>
      </div>

      <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 text-center">
        <div class="text-[10px] text-gray-400 uppercase font-semibold">{{ t('mc_host_uptime') }}</div>
        <div class="text-lg font-extrabold text-purple-300 mt-0.5">
          {{ formatUptime(mcStatus?.uptime) }}
        </div>
        <div class="text-[10px] text-gray-400 mt-1">
          Kernel-grade telemetry
        </div>
      </div>
    </div>

    <!-- Section 1: Global Incident Thresholds -->
    <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative space-y-4">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>// {{ t('mc_thresholds_title') }}</span>
          </h3>
          <p class="text-xs text-gray-400 font-mono mt-0.5">
            {{ t('mc_thresholds_subtitle') }}
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button
            @click="handleResetThresholds"
            :disabled="savingThresholds"
            class="px-2.5 py-1 text-xs font-mono font-bold rounded bg-gray-900 hover:bg-gray-800 text-gray-300 border border-gray-700 transition cursor-pointer"
          >
            {{ t('mc_reset_defaults') }}
          </button>
          <button
            @click="handleSaveThresholds"
            :disabled="savingThresholds"
            class="px-3 py-1 text-xs font-mono font-bold rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white transition cursor-pointer flex items-center gap-1.5"
          >
            <span>{{ savingThresholds ? t('saving', 'Menyimpan...') : t('mc_save_thresholds') }}</span>
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
        <!-- CPU Card -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="font-bold text-gray-200 flex items-center justify-between">
            <span>CPU Processor Load</span>
            <span class="text-[10px] text-cyan-400">Warning ≤ Major ≤ Danger</span>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-[10px] text-yellow-400 block font-semibold">Warning (%)</label>
              <input v-model.number="thForm.cpu_warn" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-amber-400 block font-semibold">Major (%)</label>
              <input v-model.number="thForm.cpu_average" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-rose-400 block font-semibold">Danger (%)</label>
              <input v-model.number="thForm.cpu_danger" type="number" step="0.5" class="th-input" />
            </div>
          </div>
        </div>

        <!-- RAM Card -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="font-bold text-gray-200 flex items-center justify-between">
            <span>Memory RAM Usage</span>
            <span class="text-[10px] text-emerald-400">Warning ≤ Major ≤ Danger</span>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-[10px] text-yellow-400 block font-semibold">Warning (%)</label>
              <input v-model.number="thForm.ram_warn" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-amber-400 block font-semibold">Major (%)</label>
              <input v-model.number="thForm.ram_average" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-rose-400 block font-semibold">Danger (%)</label>
              <input v-model.number="thForm.ram_danger" type="number" step="0.5" class="th-input" />
            </div>
          </div>
        </div>

        <!-- Disk Card -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="font-bold text-gray-200 flex items-center justify-between">
            <span>Storage Disk Capacity</span>
            <span class="text-[10px] text-purple-400">Warning ≤ Major ≤ Danger</span>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-[10px] text-yellow-400 block font-semibold">Warning (%)</label>
              <input v-model.number="thForm.disk_warn" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-amber-400 block font-semibold">Major (%)</label>
              <input v-model.number="thForm.disk_average" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-rose-400 block font-semibold">Danger (%)</label>
              <input v-model.number="thForm.disk_danger" type="number" step="0.5" class="th-input" />
            </div>
          </div>
        </div>

        <!-- Swap & SSH Card -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="font-bold text-gray-200 flex items-center justify-between">
            <span>Swap & SSH Auth Failures</span>
            <span class="text-[10px] text-blue-400">Thresholds</span>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-[10px] text-yellow-400 block font-semibold">Swap Warn (%)</label>
              <input v-model.number="thForm.swap_warn" type="number" step="0.5" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-yellow-400 block font-semibold">SSH Warn (Att)</label>
              <input v-model.number="thForm.ssh_fail_warn" type="number" step="1" class="th-input" />
            </div>
            <div>
              <label class="text-[10px] text-rose-400 block font-semibold">SSH Danger (Att)</label>
              <input v-model.number="thForm.ssh_fail_danger" type="number" step="1" class="th-input" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 2: MySQL Database Storage & Table Optimization -->
    <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative space-y-4">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>// {{ t('mc_db_storage_title') }}</span>
          </h3>
          <p class="text-xs text-gray-400 font-mono mt-0.5">
            {{ t('mc_db_storage_subtitle') }}
          </p>
        </div>

        <button
          @click="handleOptimizeDb"
          :disabled="optimizingDb"
          class="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer flex items-center gap-1.5 shadow-sm"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          <span>{{ optimizingDb ? 'Optimizing...' : t('mc_optimize_db_btn') }}</span>
        </button>
      </div>

      <!-- Table Storage Breakdown -->
      <div class="overflow-x-auto border border-gray-800/80 rounded-lg">
        <table class="w-full text-left font-mono border-collapse text-xs">
          <thead>
            <tr class="bg-[#0b1220] border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3">{{ t('mc_col_table_name') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('mc_col_est_rows') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('mc_col_table_size') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('mc_col_storage_share') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr
              v-for="tbl in mcStatus?.database?.tables || []"
              :key="tbl.table"
              class="hover:bg-gray-800/20 transition-colors"
            >
              <td class="py-2.5 px-3 font-bold text-gray-200">{{ tbl.table }}</td>
              <td class="py-2.5 px-3 text-right text-gray-400">{{ Number(tbl.rows).toLocaleString() }}</td>
              <td class="py-2.5 px-3 text-right font-bold text-cyan-300">{{ tbl.size_mb }} MB</td>
              <td class="py-2.5 px-3 text-right text-gray-400">
                {{ getTablePercentage(tbl.size_mb) }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from '../../i18n'
import { formatBytes, formatUptime } from '../../utils/formatters'
import { confirmAction } from '../../utils/useToast'

const { t } = useI18n()

const mcStatus = ref(null)
const flashMsg = ref('')
const flashType = ref('success')
const savingThresholds = ref(false)
const optimizingDb = ref(false)

const thForm = reactive({
  cpu_warn: 85.0,
  cpu_average: 90.0,
  cpu_danger: 95.0,
  ram_warn: 85.0,
  ram_average: 90.0,
  ram_danger: 95.0,
  disk_warn: 90.0,
  disk_average: 92.5,
  disk_danger: 95.0,
  swap_warn: 80.0,
  swap_average: 86.0,
  swap_danger: 92.0,
  ssh_fail_warn: 5,
  ssh_fail_danger: 10,
})

onMounted(() => {
  loadMasterControlStatus()
  loadThresholds()
})

async function loadMasterControlStatus() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/master-control/status', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      mcStatus.value = await res.json()
    }
  } catch (err) {
    console.error('Failed to load Master Control status:', err)
  }
}

async function loadThresholds() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/settings/thresholds', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      if (data.thresholds) {
        Object.assign(thForm, data.thresholds)
      }
    }
  } catch (err) {
    console.error('Failed to load thresholds:', err)
  }
}

async function handleSaveThresholds() {
  savingThresholds.value = true
  flashMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/settings/thresholds', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(thForm),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to save thresholds')
    flashType.value = 'success'
    flashMsg.value = 'Global incident thresholds updated successfully.'
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  } finally {
    savingThresholds.value = false
  }
}

async function handleResetThresholds() {
  const ok = await confirmAction({
    title: 'Reset Incident Thresholds',
    message: 'Reset all incident thresholds to system defaults?',
    confirmText: 'Reset Defaults',
    variant: 'warning',
  })
  if (!ok) return
  savingThresholds.value = true
  flashMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/settings/thresholds/reset', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to reset thresholds')
    if (data.thresholds) Object.assign(thForm, data.thresholds)
    flashType.value = 'success'
    flashMsg.value = 'Incident thresholds reset to defaults.'
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  } finally {
    savingThresholds.value = false
  }
}

async function handleOptimizeDb() {
  const ok = await confirmAction({
    title: 'Optimize Database Tables',
    message: 'Execute SQL OPTIMIZE TABLE commands to defragment and reclaim storage space?',
    confirmText: 'Optimize Now',
    variant: 'warning',
  })
  if (!ok) return
  optimizingDb.value = true
  flashMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/master-control/optimize-db', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to optimize database')
    flashType.value = 'success'
    flashMsg.value = data.message || 'Database optimization completed successfully.'
    loadMasterControlStatus()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  } finally {
    optimizingDb.value = false
  }
}

function getTablePercentage(sizeMb) {
  const total = mcStatus.value?.database?.total_size_mb || 0
  if (!total) return 0
  return ((sizeMb / total) * 100).toFixed(1)
}
</script>

<style scoped>
.th-input {
  width: 100%;
  background-color: #111827;
  border: 1px solid #1f2937;
  color: #f3f4f6;
  font-size: 11px;
  border-radius: 4px;
  padding: 4px 6px;
  margin-top: 2px;
  outline: none;
}
.th-input:focus {
  border-color: #06b6d4;
}
</style>
