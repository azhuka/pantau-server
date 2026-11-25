<template>
  <NocFilterPanel
    class="relative z-30"
    :has-active-filters="hasActiveFilters"
    :summary-text="`${filteredCount} of ${totalCount} assets`"
    @reset="$emit('reset')"
  >
    <template #fields>
      <!-- 1. Asset Group Filter -->
      <div class="noc-filter-col" title="Filter by Asset Group">
        <label class="noc-filter-label" for="assets-group-filter">{{ t('flt_group') }}</label>
        <select
          id="assets-group-filter"
          :value="group"
          @change="$emit('update:group', $event.target.value)"
          class="noc-filter-select max-w-[175px]"
        >
          <option value="">{{ t('flt_all_groups') }} ({{ totalCount }})</option>
          <option v-for="g in groupMeta.groups" :key="g" :value="g">
            {{ g }} ({{ groupMeta.counts[g] }})
          </option>
          <option v-if="groupMeta.ungroupedCount > 0" value="__none__">
            {{ t('flt_ungrouped') }} ({{ groupMeta.ungroupedCount }})
          </option>
        </select>
      </div>

      <!-- 2. Connectivity & Health Status Filter -->
      <div class="noc-filter-col" title="Filter by Operational Status">
        <label class="noc-filter-label" for="assets-status-filter">{{ t('flt_status') }}</label>
        <select
          id="assets-status-filter"
          :value="status"
          @change="$emit('update:status', $event.target.value)"
          class="noc-filter-select"
        >
          <option value="all">{{ t('flt_all_statuses') }}</option>
          <option value="online">{{ t('online') }}</option>
          <option value="offline">{{ t('offline') }}</option>
          <option value="problem">{{ t('flt_status_with_incidents') }}</option>
          <option value="maint">{{ t('flt_status_maint') }}</option>
        </select>
      </div>

      <!-- 3. Environment / Tier Filter -->
      <div class="noc-filter-col" title="Filter by Environment Classification">
        <label class="noc-filter-label" for="assets-tier-filter">{{ t('flt_env') }}</label>
        <select
          id="assets-tier-filter"
          :value="tier"
          @change="$emit('update:tier', $event.target.value)"
          class="noc-filter-select"
        >
          <option value="">{{ t('flt_all_envs') }}</option>
          <option value="1">{{ t('flt_env_prod') }}</option>
          <option value="2">{{ t('flt_env_nonprod') }}</option>
        </select>
      </div>

      <!-- 4. Comprehensive Search -->
      <div class="noc-filter-col-search" title="Search hostname, IP, group, tags, OS, kernel, CPU, notes">
        <label class="noc-filter-label" for="assets-search-input">{{ t('flt_search') }}</label>
        <div class="noc-filter-search-box">
          <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            id="assets-search-input"
            :value="search"
            @input="$emit('update:search', $event.target.value)"
            type="search"
            :placeholder="t('search_placeholder')"
          />
        </div>
      </div>
    </template>

    <template #actions>
      <ColumnCustomizerDropdown
        :columns="columns"
        @toggle="(id, v) => $emit('toggle-col', id, v)"
        @preset="(p) => $emit('preset-col', p)"
        @reset="$emit('reset-col')"
      />
    </template>
  </NocFilterPanel>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../i18n'
import { extractGroupOptions } from '../../utils/filterHelpers'
import NocFilterPanel from '../common/NocFilterPanel.vue'
import ColumnCustomizerDropdown from './ColumnCustomizerDropdown.vue'

const { t } = useI18n()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  group: { type: String, default: '' },
  status: { type: String, default: 'all' },
  tier: { type: String, default: '' },
  search: { type: String, default: '' },
  columns: { type: Array, default: () => [] },
  filteredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
})

defineEmits([
  'update:group', 'update:status', 'update:tier', 'update:search',
  'reset', 'toggle-col', 'preset-col', 'reset-col'
])

const groupMeta = computed(() => extractGroupOptions(props.servers))

const hasActiveFilters = computed(() => Boolean(
  props.group || (props.status && props.status !== 'all') || props.tier || props.search.trim()
))
</script>
