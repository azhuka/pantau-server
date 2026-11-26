<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>

    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">APT PACKAGES &amp; UPDATES</h3>
        <button
          type="button"
          @click="statusFilter = 'all'"
          class="px-2 py-0.5 rounded text-[11px] bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 hover:border-cyan-400 cursor-pointer"
        >
          {{ (packagesList || []).length }} installed
        </button>
      </div>
      <button
        type="button"
        @click="statusFilter = statusFilter === 'upgradable' ? 'all' : 'upgradable'"
        class="px-2 py-0.5 rounded text-xs font-bold border transition cursor-pointer"
        :class="statusFilter === 'upgradable' ? 'bg-amber-950 text-amber-200 border-amber-400' : 'bg-amber-950/40 text-amber-300 border-amber-800/50 hover:border-amber-500'"
        title="Click to filter upgradable packages (click again to show all)"
      >
        {{ upgradableTotal }} upgradable
      </button>
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
            <input id="pkg-search-input" v-model="search" type="search" placeholder="Search package, version, description..." />
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
            <option value="installed">Installed</option>
          </select>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="paginatedPackages.length === 0" class="text-xs text-gray-400 py-8 text-center">
      No packages match the selected criteria.
    </div>
    <div v-else class="overflow-x-auto max-h-[430px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold">
          <tr>
            <th class="py-2 px-3">{{ t('col_pkg_name') }}</th>
            <th class="py-2 px-3">{{ t('col_pkg_current') }}</th>
            <th class="py-2 px-3">{{ t('col_pkg_new') }}</th>
            <th class="py-2 px-3">{{ t('ws_col_description') }}</th>
            <th v-if="canApt" class="py-2 px-3 text-center w-20">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(pkg, idx) in paginatedPackages" :key="pkg.name + idx" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 font-semibold text-gray-200 whitespace-nowrap">
              <span>{{ pkg.name }}</span>
              <span v-if="pkg.is_user" class="ml-1.5 text-[10px] px-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">app</span>
            </td>
            <td class="py-2 px-3 text-gray-400 whitespace-nowrap">{{ pkg.current_version || pkg.version || '-' }}</td>
            <td class="py-2 px-3 whitespace-nowrap font-bold" :class="pkg.status === 'upgradable' ? 'text-amber-300' : 'text-emerald-400'">
              {{ pkg.candidate_version || pkg.new_version || (pkg.status === 'upgradable' ? 'update ready' : 'up-to-date') }}
            </td>
            <td class="py-2 px-3 text-gray-400 truncate max-w-sm" :title="pkg.summary || ''">{{ pkg.summary || '-' }}</td>
            <td v-if="canApt" class="py-2 px-3 text-center">
              <button
                type="button"
                :disabled="!isOnline || (pkg.status !== 'upgradable' && !pkg.candidate_version)"
                @click="$emit('upgrade-package', pkg.name)"
                class="inline-flex items-center justify-center rounded border transition"
                style="width: 26px; height: 26px; min-width: 26px; border-radius: 4px;"
                :class="(!isOnline || (pkg.status !== 'upgradable' && !pkg.candidate_version))
                  ? 'border-gray-800 bg-gray-900/40 text-gray-500 opacity-40 cursor-not-allowed'
                  : 'border-amber-700/60 bg-amber-950/50 text-amber-300 hover:bg-amber-900/70 hover:text-white cursor-pointer'"
                :title="!isOnline ? 'Asset is offline' : ((pkg.status !== 'upgradable' && !pkg.candidate_version) ? 'Package is already up-to-date' : `Upgrade ${pkg.name}`)"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination
      v-model:page="currentPage"
      v-model:pageSize="pageSize"
      :total="filteredPackages.length"
      unitLabel="packages"
      :pageSizeOptions="[10, 25, 50, 100, 'all']"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  server: { type: Object, default: () => ({}) },
  packagesList: { type: Array, default: () => [] },
  canApt: { type: Boolean, default: false },
  isOnline: { type: Boolean, default: true },
})

defineEmits(['upgrade-package'])

const search = ref('')
const typeFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)

watch([search, typeFilter, statusFilter], () => { currentPage.value = 1 })

const upgradableTotal = computed(() => {
  const fromList = (props.packagesList || []).filter(p => p.status === 'upgradable' || p.candidate_version).length
  return Math.max(fromList, Number(props.server?.apt_upgradable || 0))
})

const filteredPackages = computed(() => {
  return (props.packagesList || []).filter(pkg => {
    if (typeFilter.value === 'user' && !pkg.is_user) return false
    if (typeFilter.value === 'system' && pkg.is_user) return false
    if (statusFilter.value === 'upgradable' && pkg.status !== 'upgradable' && !pkg.candidate_version) return false
    if (statusFilter.value === 'installed' && (pkg.status === 'upgradable' || pkg.candidate_version)) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = `${pkg.name || ''} ${pkg.current_version || pkg.version || ''} ${pkg.candidate_version || ''} ${pkg.summary || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const paginatedPackages = computed(() => {
  if (pageSize.value === 'all') return filteredPackages.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredPackages.value.slice(start, start + limit)
})
</script>
