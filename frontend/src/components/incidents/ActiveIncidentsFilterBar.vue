<template>
  <div class="space-y-2.5 my-2.5">
    <!-- Severity Triage Pills with Live Counts (2-Way Synced with Severity Dropdown) -->
    <div class="flex flex-wrap items-center gap-1.5 font-mono">
      <button
        v-for="pill in pillDefs"
        :key="pill.key"
        type="button"
        @click="$emit('update:severity', pill.key)"
        class="px-2.5 py-1 rounded-md text-[11px] font-bold border transition cursor-pointer inline-flex items-center gap-1.5"
        :class="severity === pill.key ? pill.activeCls : 'bg-[#060a14] border-gray-800 text-gray-400 hover:text-gray-200 hover:border-gray-700'"
      >
        <span>{{ pill.label }}</span>
        <span class="px-1.5 py-0.2 rounded-full text-[10px] bg-black/40 border border-white/10">{{ pill.count }}</span>
      </button>
    </div>

    <!-- Unified NOC Filter Panel -->
    <NocFilterPanel
      :has-active-filters="hasActiveFilters"
      :summary-text="`${filteredCount} of ${totalCount} incidents`"
      compact
      @reset="$emit('reset')"
    >
      <template #fields>
        <!-- Asset Dropdown -->
        <div class="noc-filter-col" title="Filter by Asset Host">
          <label class="noc-filter-label" for="inc-active-asset">{{ t('flt_asset') }}</label>
          <select
            id="inc-active-asset"
            :value="serverId"
            @change="$emit('update:serverId', $event.target.value)"
            class="noc-filter-select max-w-[175px]"
          >
            <option value="">{{ t('flt_all_assets') }}</option>
            <option v-for="srv in servers" :key="srv.id" :value="String(srv.id)">
              {{ srv.hostname }}
            </option>
          </select>
        </div>

        <!-- Group Dropdown -->
        <div class="noc-filter-col" title="Filter by Asset Group">
          <label class="noc-filter-label" for="inc-active-group">{{ t('flt_group') }}</label>
          <select
            id="inc-active-group"
            :value="group"
            @change="$emit('update:group', $event.target.value)"
            class="noc-filter-select max-w-[165px]"
          >
            <option value="">{{ t('flt_all_groups') }}</option>
            <option v-for="g in groupMeta.groups" :key="g" :value="g">{{ g }}</option>
            <option v-if="groupMeta.ungroupedCount > 0" value="__none__">{{ t('flt_ungrouped') }}</option>
          </select>
        </div>

        <!-- Severity Dropdown (Synced 2-way with Pills) -->
        <div class="noc-filter-col" title="Filter by Incident Severity">
          <label class="noc-filter-label" for="inc-active-sev">{{ t('flt_severity') }}</label>
          <select
            id="inc-active-sev"
            :value="severity"
            @change="$emit('update:severity', $event.target.value)"
            class="noc-filter-select"
          >
            <option value="all">{{ t('flt_all_severities') }}</option>
            <option value="danger">{{ t('inc_filter_danger') }}</option>
            <option value="critical">{{ t('inc_filter_critical') }}</option>
            <option value="warning">{{ t('inc_filter_warning') }}</option>
            <option value="info">{{ t('inc_filter_info') }}</option>
            <option value="ignored">{{ t('inc_filter_ignored') }}</option>
          </select>
        </div>

        <!-- Search Input -->
        <div class="noc-filter-col-search" title="Search asset, group, event, or key">
          <label class="noc-filter-label" for="inc-active-search">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              id="inc-active-search"
              :value="search"
              @input="$emit('update:search', $event.target.value)"
              type="search"
              :placeholder="t('inc_search_placeholder')"
            />
          </div>
        </div>
      </template>
    </NocFilterPanel>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../i18n'
import { extractGroupOptions } from '../../utils/filterHelpers'
import NocFilterPanel from '../common/NocFilterPanel.vue'

const { t } = useI18n()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  pillCounts: { type: Object, default: () => ({ all: 0, danger: 0, critical: 0, warning: 0, info: 0, ignored: 0 }) },
  serverId: { type: String, default: '' },
  group: { type: String, default: '' },
  severity: { type: String, default: 'all' },
  search: { type: String, default: '' },
  filteredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
})

defineEmits(['update:serverId', 'update:group', 'update:severity', 'update:search', 'reset'])

const groupMeta = computed(() => extractGroupOptions(props.servers))

const hasActiveFilters = computed(() => Boolean(props.serverId || props.group || props.severity !== 'all' || props.search.trim()))

const pillDefs = computed(() => [
  { key: 'all', label: t('inc_filter_all'), count: props.pillCounts.all || 0, activeCls: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50' },
  { key: 'danger', label: t('inc_filter_danger'), count: props.pillCounts.danger || 0, activeCls: 'bg-rose-500/20 text-rose-300 border-rose-500/50' },
  { key: 'critical', label: t('inc_filter_critical'), count: props.pillCounts.critical || 0, activeCls: 'bg-orange-500/20 text-orange-300 border-orange-500/50' },
  { key: 'warning', label: t('inc_filter_warning'), count: props.pillCounts.warning || 0, activeCls: 'bg-amber-500/20 text-amber-300 border-amber-500/50' },
  { key: 'info', label: t('inc_filter_info'), count: props.pillCounts.info || 0, activeCls: 'bg-blue-500/20 text-blue-300 border-blue-500/50' },
  { key: 'ignored', label: t('inc_filter_ignored'), count: props.pillCounts.ignored || 0, activeCls: 'bg-slate-600/30 text-gray-200 border-slate-500/60' },
])
</script>
