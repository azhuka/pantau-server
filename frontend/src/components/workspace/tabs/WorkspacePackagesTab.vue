<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>

    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">Packages</h3>
        <button
          type="button"
          @click="statusFilter = 'all'"
          class="px-2 py-0.5 rounded text-[11px] bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 hover:border-cyan-400 cursor-pointer"
          title="Show all installed packages"
        >
          {{ (packagesList || []).length }} installed
        </button>
        <button
          v-if="upgradableTotal > 0"
          type="button"
          @click="statusFilter = statusFilter === 'upgradable' ? 'all' : 'upgradable'"
          class="px-2 py-0.5 rounded text-[11px] font-bold border transition cursor-pointer"
          :class="statusFilter === 'upgradable' ? 'bg-amber-950 text-amber-200 border-amber-400' : 'bg-amber-950/40 text-amber-300 border-amber-800/50 hover:border-amber-500'"
          title="Filter upgradable packages (click again to reset)"
        >
          {{ upgradableTotal }} upgradable
        </button>
      </div>

      <div class="flex items-center gap-1.5">
        <button
          type="button"
          :disabled="!isOnline || refreshing"
          @click="$emit('refresh-packages')"
          class="w-[26px] h-[26px] rounded border transition inline-flex items-center justify-center"
          :class="!isOnline || refreshing ? 'border-gray-800 bg-gray-900/40 text-gray-500 opacity-40 cursor-not-allowed' : 'border-gray-700 bg-gray-900 text-gray-300 hover:bg-cyan-950 hover:text-cyan-300 hover:border-cyan-600/50 cursor-pointer'"
          :title="!isOnline ? 'Asset is offline' : (refreshing ? 'Refreshing package inventory...' : 'Refresh packages list from host')"
        >
          <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': refreshing }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
        </button>
        <button
          v-if="canApt && !isViewer"
          type="button"
          :disabled="!isOnline || upgradableTotal <= 0 || aptTaskRunning"
          @click="$emit('upgrade-all')"
          class="w-[26px] h-[26px] rounded border transition inline-flex items-center justify-center"
          :class="(!isOnline || upgradableTotal <= 0 || aptTaskRunning) ? 'border-gray-800 bg-gray-900/40 text-gray-500 opacity-40 cursor-not-allowed' : 'border-amber-700/60 bg-amber-950/50 text-amber-300 hover:bg-amber-900/70 hover:text-white cursor-pointer'"
          :title="!isOnline ? 'Asset is offline' : (aptTaskRunning ? 'Another APT task is currently running' : (upgradableTotal <= 0 ? 'All packages are up-to-date' : `Upgrade all ${upgradableTotal} upgradable packages`))"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="16 12 12 8 8 12"/><line x1="12" y1="16" x2="12" y2="8"/></svg>
        </button>
      </div>
    </div>

    <NocFilterPanel
      :has-active-filters="Boolean(typeFilter !== 'all' || statusFilter !== 'all' || search.trim())"
      :summary-text="`${filteredPackages.length} of ${(packagesList || []).length} packages`"
      compact
      @reset="typeFilter = 'all'; statusFilter = 'all'; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="pkg-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="pkg-search-input" v-model="search" type="search" placeholder="Search package, version, arch, description..." />
          </div>
        </div>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="pkg-type-filter">{{ t('flt_pkg_type') }}</label>
          <select id="pkg-type-filter" v-model="typeFilter" class="noc-filter-select">
            <option value="all">{{ t('flt_pkg_all_types') }}</option>
            <option value="user">{{ t('flt_pkg_user') }}</option>
            <option value="system">{{ t('flt_pkg_system') }}</option>
          </select>
        </div>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="pkg-status-filter">{{ t('flt_status') }}</label>
          <select id="pkg-status-filter" v-model="statusFilter" class="noc-filter-select">
            <option value="all">{{ t('flt_all_statuses') }}</option>
            <option value="upgradable">Upgradable Available</option>
            <option value="running">running</option>
            <option value="exited">exited (active)</option>
            <option value="failed">failed</option>
            <option value="inactive">inactive</option>
            <option value="installed">installed</option>
          </select>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="paginatedPackages.length === 0" class="text-xs text-gray-400 py-8 text-center">
      {{ (packagesList || []).length === 0 ? 'No package inventory cached yet. Click Refresh above to scan packages.' : 'No packages match the selected criteria.' }}
    </div>
    <div v-else class="overflow-x-auto max-h-[430px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold">
          <tr>
            <th class="py-2 px-3 cursor-pointer select-none whitespace-nowrap" @click="toggleSort('status')">{{ t('col_pkg_status') }} <span class="text-[10px] opacity-70">{{ sortIcon('status') }}</span></th>
            <th class="py-2 px-3 cursor-pointer select-none whitespace-nowrap" @click="toggleSort('name')">{{ t('col_pkg_name') }} <span class="text-[10px] opacity-70">{{ sortIcon('name') }}</span></th>
            <th class="py-2 px-3 text-center cursor-pointer select-none whitespace-nowrap" @click="toggleSort('is_user')">{{ t('col_pkg_type') }} <span class="text-[10px] opacity-70">{{ sortIcon('is_user') }}</span></th>
            <th class="py-2 px-3 cursor-pointer select-none whitespace-nowrap" @click="toggleSort('current_version')">{{ t('col_pkg_version') }} <span class="text-[10px] opacity-70">{{ sortIcon('current_version') }}</span></th>
            <th class="py-2 px-3 text-right cursor-pointer select-none whitespace-nowrap" @click="toggleSort('size_kb')">{{ t('col_pkg_size') }} <span class="text-[10px] opacity-70">{{ sortIcon('size_kb') }}</span></th>
            <th class="py-2 px-3">{{ t('ws_col_description') }}</th>
            <th class="py-2 px-3 text-center w-24">{{ t('col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(pkg, idx) in paginatedPackages" :key="pkg.name + idx" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 whitespace-nowrap">
              <span class="px-1.5 py-0.5 rounded text-[10px] font-bold border" :class="statusBadgeClass(pkg.status)">{{ pkg.status || 'installed' }}</span>
            </td>
            <td class="py-2 px-3 font-semibold text-gray-200 whitespace-nowrap">
              <span>{{ pkg.name }}</span>
              <span v-if="pkg.arch" class="ml-1.5 text-[10px] px-1 rounded bg-gray-900 text-gray-400 border border-gray-700/70">{{ pkg.arch }}</span>
            </td>
            <td class="py-2 px-3 text-center whitespace-nowrap">
              <span class="px-1.5 py-0.5 rounded text-[10px] border" :class="pkg.is_user ? 'bg-cyan-950 text-cyan-300 border-cyan-800/60' : 'bg-gray-900 text-gray-400 border-gray-800'">
                {{ pkg.is_user ? 'App' : 'System' }}
              </span>
            </td>
            <td class="py-2 px-3 whitespace-nowrap text-gray-300">
              <span>{{ pkg.current_version || pkg.version || '-' }}</span>
              <span v-if="isUpgradable(pkg)" class="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-950/70 text-amber-300 border border-amber-700/60" :title="`Update available: ${pkg.candidate_version || pkg.new_version}`">
                ↑ {{ pkg.candidate_version || pkg.new_version || 'update' }}
              </span>
            </td>
            <td class="py-2 px-3 text-right text-gray-400 whitespace-nowrap">{{ formatSize(pkg.size_kb) }}</td>
            <td class="py-2 px-3 text-gray-400 truncate max-w-xs" :title="pkg.summary || ''">{{ pkg.summary || '-' }}</td>
            <td class="py-2 px-3 text-center whitespace-nowrap">
              <button
                v-if="!canApt || isViewer"
                type="button"
                @click="$emit('view-logs', pkg.name)"
                class="w-[26px] h-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 inline-flex items-center justify-center cursor-pointer"
                :title="`View dpkg/apt logs for ${pkg.name}`"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button
                v-else
                type="button"
                @click.stop="openMenu(pkg, $event)"
                class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                :title="`Actions for ${pkg.name}`"
              >
                <span>Actions</span><span class="text-[9px]">▾</span>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="sortedPackages.length" unitLabel="packages" :pageSizeOptions="[10, 25, 50, 100, 'all']" />

    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div class="py-0.5">
          <button
            type="button"
            :disabled="!isOnline || !isUpgradable(menuTarget) || aptTaskRunning"
            @click="act('upgrade-package', menuTarget.name)"
            class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="!isOnline ? 'Asset is offline' : (!isUpgradable(menuTarget) ? 'Package is already up-to-date' : (aptTaskRunning ? 'Another APT task is running' : `Upgrade ${menuTarget.name}`))"
          >
            {{ isUpgradable(menuTarget) ? 'Upgrade Package' : 'Up-to-date' }}
          </button>
          <button
            type="button"
            :disabled="!isOnline"
            @click="act('view-logs', menuTarget.name)"
            class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? `View dpkg/apt logs for ${menuTarget.name}` : 'Asset is offline'"
          >
            View Logs
          </button>
          <button
            type="button"
            :disabled="!isOnline"
            @click="act('clear-cache', menuTarget.name)"
            class="w-full px-3 py-1.5 text-left text-gray-300 hover:bg-gray-800/80 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? `Clear apt archive cache for ${menuTarget.name}` : 'Asset is offline'"
          >
            Clear Cache
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  server: { type: Object, default: () => ({}) },
  packagesList: { type: Array, default: () => [] },
  canApt: { type: Boolean, default: false },
  isViewer: { type: Boolean, default: false },
  isOnline: { type: Boolean, default: true },
  aptTaskRunning: { type: Boolean, default: false },
  refreshing: { type: Boolean, default: false },
})

const emit = defineEmits(['upgrade-package', 'upgrade-all', 'refresh-packages', 'clear-cache', 'view-logs'])

const search = ref('')
const typeFilter = ref('all')
const statusFilter = ref('all')
const sortCol = ref('')
const sortDir = ref('asc')
const currentPage = ref(1)
const pageSize = ref(10)
const menuTarget = ref(null)
const dropdownPos = ref({ top: 0, left: 0 })

watch([search, typeFilter, statusFilter], () => { currentPage.value = 1 })

const isUpgradable = (pkg) => Boolean(pkg?.is_upgradable || pkg?.status === 'upgradable' || pkg?.candidate_version)

const upgradableTotal = computed(() => {
  const fromList = (props.packagesList || []).filter(isUpgradable).length
  return Math.max(fromList, Number(props.server?.apt_upgradable || 0))
})

const filteredPackages = computed(() => {
  return (props.packagesList || []).filter(pkg => {
    if (typeFilter.value === 'user' && !pkg.is_user) return false
    if (typeFilter.value === 'system' && pkg.is_user) return false
    const st = (pkg.status || 'installed').toLowerCase()
    if (statusFilter.value === 'upgradable' && !isUpgradable(pkg)) return false
    else if (statusFilter.value === 'exited' && !st.startsWith('exited')) return false
    else if (['running', 'failed', 'inactive', 'installed'].includes(statusFilter.value) && st !== statusFilter.value) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = `${pkg.name || ''} ${pkg.current_version || pkg.version || ''} ${pkg.candidate_version || ''} ${pkg.arch || ''} ${pkg.summary || ''} ${st}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const sortedPackages = computed(() => {
  const list = [...filteredPackages.value]
  if (!sortCol.value) return list
  const dir = sortDir.value === 'asc' ? 1 : -1
  return list.sort((a, b) => {
    if (sortCol.value === 'size_kb') return (Number(a.size_kb || 0) - Number(b.size_kb || 0)) * dir
    if (sortCol.value === 'is_user') return ((a.is_user ? 1 : 0) - (b.is_user ? 1 : 0)) * dir
    const va = String(a[sortCol.value] || '').toLowerCase()
    const vb = String(b[sortCol.value] || '').toLowerCase()
    return va.localeCompare(vb) * dir
  })
})

const paginatedPackages = computed(() => {
  if (pageSize.value === 'all') return sortedPackages.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return sortedPackages.value.slice(start, start + limit)
})

function toggleSort(col) {
  if (sortCol.value === col) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortCol.value = col; sortDir.value = col === 'size_kb' ? 'desc' : 'asc' }
}

const sortIcon = (col) => (sortCol.value !== col ? '↕' : (sortDir.value === 'asc' ? '▲' : '▼'))

function statusBadgeClass(st) {
  const s = (st || 'installed').toLowerCase()
  if (s === 'running') return 'bg-emerald-950/60 text-emerald-300 border-emerald-700/60'
  if (s.startsWith('exited')) return 'bg-cyan-950/60 text-cyan-300 border-cyan-700/60'
  if (s === 'failed') return 'bg-rose-950/60 text-rose-300 border-rose-700/60'
  if (s === 'inactive') return 'bg-amber-950/60 text-amber-300 border-amber-700/60'
  return 'bg-gray-900 text-gray-400 border-gray-700/60'
}

function formatSize(kb) {
  const n = Number(kb || 0)
  if (n >= 1024) return `${(n / 1024).toFixed(1)} MB`
  return n > 0 ? `${n} KB` : '-'
}

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  minWidth: '165px',
}))

function openMenu(pkg, event) {
  if (menuTarget.value?.name === pkg.name) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = { top: Math.min(rect.bottom + 4, window.innerHeight - 130), left: Math.max(8, rect.right - 165) }
  menuTarget.value = pkg
}

function act(eventName, pkgName) {
  menuTarget.value = null
  emit(eventName, pkgName)
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => window.addEventListener('click', closeMenu))
onUnmounted(() => window.removeEventListener('click', closeMenu))
</script>
