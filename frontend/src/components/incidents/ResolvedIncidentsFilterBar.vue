<template>
  <NocFilterPanel
    class="my-2.5"
    :has-active-filters="hasActiveFilters"
    :summary-text="`${filteredCount} of ${totalCount} resolved incidents`"
    compact
    @reset="$emit('reset')"
  >
    <template #fields>
      <!-- 1. Asset Filter -->
      <div class="noc-filter-col" title="Filter by Asset Host">
        <label class="noc-filter-label" for="res-filter-asset">{{ t('flt_asset') }}</label>
        <select
          id="res-filter-asset"
          :value="serverId"
          @change="$emit('update:serverId', $event.target.value)"
          class="noc-filter-select max-w-[165px]"
        >
          <option value="">{{ t('flt_all_assets') }}</option>
          <option v-for="srv in servers" :key="srv.id" :value="String(srv.id)">
            {{ srv.hostname }}
          </option>
        </select>
      </div>

      <!-- 2. Severity Filter -->
      <div class="noc-filter-col" title="Filter by Incident Severity">
        <label class="noc-filter-label" for="res-filter-sev">{{ t('flt_severity') }}</label>
        <select
          id="res-filter-sev"
          :value="severity"
          @change="$emit('update:severity', $event.target.value)"
          class="noc-filter-select"
        >
          <option value="">{{ t('flt_all_severities') }}</option>
          <option value="danger">{{ t('inc_filter_danger') }}</option>
          <option value="critical">{{ t('inc_filter_critical') }}</option>
          <option value="warning">{{ t('inc_filter_warning') }}</option>
          <option value="info">{{ t('inc_filter_info') }}</option>
        </select>
      </div>

      <!-- 3. Resolution Type Filter (7 Blueprint Categories) -->
      <div class="noc-filter-col" title="Filter by Resolution Mode">
        <label class="noc-filter-label" for="res-filter-type">{{ t('flt_resolution') }}</label>
        <select
          id="res-filter-type"
          :value="resType"
          @change="$emit('update:resType', $event.target.value)"
          class="noc-filter-select max-w-[195px]"
        >
          <option value="all">{{ t('inc_type_all') }}</option>
          <option value="auto">{{ t('inc_type_auto') }}</option>
          <option value="manual">{{ t('inc_type_manual') }}</option>
          <option value="online">{{ t('inc_type_online') }}</option>
          <option value="service_up">{{ t('inc_type_service_up') }}</option>
          <option value="stale_closed">{{ t('inc_type_stale_closed') }}</option>
          <option value="session_closed">{{ t('inc_type_session_closed') }}</option>
          <option value="dedup">{{ t('inc_type_dedup') }}</option>
        </select>
      </div>

      <!-- 4. Custom Date Range -->
      <div class="noc-filter-col" title="Custom resolution date range">
        <span class="noc-filter-label">{{ t('flt_date_range') }}</span>
        <div class="noc-date-range">
          <input
            id="res-date-start"
            type="date"
            :value="startDate"
            @change="onDateInput($event.target.value, endDate)"
            title="Start Date"
          />
          <span class="text-gray-500">—</span>
          <input
            id="res-date-end"
            type="date"
            :value="endDate"
            @change="onDateInput(startDate, $event.target.value)"
            title="End Date"
          />
        </div>
      </div>

      <!-- 5. Search Input -->
      <div class="noc-filter-col-search" title="Search resolved incidents">
        <label class="noc-filter-label" for="res-search-input">{{ t('flt_search') }}</label>
        <div class="noc-filter-search-box">
          <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            id="res-search-input"
            :value="search"
            @input="$emit('update:search', $event.target.value)"
            type="search"
            :placeholder="t('inc_search_placeholder')"
          />
        </div>
      </div>
    </template>

    <!-- Row 2: Quick Period Presets -->
    <template #sub>
      <span class="text-[10px] font-bold uppercase tracking-wider text-gray-400">{{ t('flt_preset') }}</span>
      <div class="inline-flex items-center gap-1 flex-wrap">
        <button
          v-for="p in presets"
          :key="p.val"
          type="button"
          class="noc-btn-preset"
          :class="{ 'is-on': period === p.val }"
          @click="selectPreset(p.val)"
        >
          {{ p.label }}
        </button>
        <button
          v-if="period === 'custom' || startDate || endDate"
          type="button"
          class="noc-btn-preset is-on"
          @click="selectPreset('custom')"
        >
          {{ t('flt_preset_custom') }}
        </button>
      </div>
    </template>
  </NocFilterPanel>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from '../../i18n'
import NocFilterPanel from '../common/NocFilterPanel.vue'

const { t } = useI18n()

const props = defineProps({
  servers: { type: Array, default: () => [] },
  period: { type: String, default: '24h' },
  startDate: { type: String, default: '' },
  endDate: { type: String, default: '' },
  serverId: { type: String, default: '' },
  severity: { type: String, default: '' },
  resType: { type: String, default: 'all' },
  search: { type: String, default: '' },
  filteredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:period', 'update:startDate', 'update:endDate',
  'update:serverId', 'update:severity', 'update:resType', 'update:search', 'reset'
])

const presets = computed(() => [
  { val: 'today', label: t('inc_period_today') },
  { val: '24h', label: t('inc_period_24h') },
  { val: '7d', label: t('inc_period_7d') },
  { val: '30d', label: t('inc_period_30d') },
  { val: 'all', label: t('inc_period_all') },
])

const hasActiveFilters = computed(() => Boolean(
  props.serverId || props.severity || props.resType !== 'all' || props.startDate || props.endDate || props.search.trim() || props.period !== '24h'
))

function selectPreset(val) {
  if (val !== 'custom') {
    emit('update:startDate', '')
    emit('update:endDate', '')
  }
  emit('update:period', val)
}

function onDateInput(s, e) {
  emit('update:startDate', s)
  emit('update:endDate', e)
  if (s || e) {
    emit('update:period', 'custom')
  } else {
    emit('update:period', '24h')
  }
}
</script>
