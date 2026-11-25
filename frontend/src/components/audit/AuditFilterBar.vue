<template>
  <NocFilterPanel
    :has-active-filters="hasActiveFilters"
    :summary-text="summaryLabel"
    @reset="$emit('reset')"
  >
    <template #fields>
      <!-- 1. Operator / User Filter -->
      <div class="noc-filter-col" title="Filter by executing operator">
        <label class="noc-filter-label" for="audit-user-filter">{{ t('flt_operator') }}</label>
        <select
          id="audit-user-filter"
          :value="user"
          @change="$emit('update:user', $event.target.value)"
          class="noc-filter-select max-w-[155px]"
        >
          <option value="">{{ t('flt_all_operators') }}</option>
          <option v-for="u in users" :key="u" :value="u">{{ u }}</option>
        </select>
      </div>

      <!-- 2. Target Server / Asset Filter -->
      <div class="noc-filter-col" title="Filter by target asset">
        <label class="noc-filter-label" for="audit-server-filter">{{ t('flt_asset') }}</label>
        <select
          id="audit-server-filter"
          :value="serverId"
          @change="$emit('update:serverId', $event.target.value)"
          class="noc-filter-select max-w-[155px]"
        >
          <option value="">{{ t('flt_all_assets') }}</option>
          <option v-for="srv in servers" :key="srv.id" :value="String(srv.id)">{{ srv.hostname }}</option>
        </select>
      </div>

      <!-- 3. Action Category & Specific Action Filter -->
      <div class="noc-filter-col" title="Filter by operation category or action">
        <label class="noc-filter-label" for="audit-action-filter">{{ t('flt_action') }}</label>
        <select
          id="audit-action-filter"
          :value="action"
          @change="$emit('update:action', $event.target.value)"
          class="noc-filter-select max-w-[190px]"
        >
          <option value="">{{ t('flt_all_actions') }}</option>
          <optgroup v-for="cat in categories" :key="cat.id" :label="cat.name">
            <option :value="cat.id">All {{ cat.name }}</option>
            <option v-for="act in cat.actions" :key="act.key" :value="act.key">{{ act.label }}</option>
          </optgroup>
        </select>
      </div>

      <!-- 4. Status Filter -->
      <div class="noc-filter-col" title="Filter execution status">
        <label class="noc-filter-label" for="audit-status-filter">{{ t('flt_status') }}</label>
        <select
          id="audit-status-filter"
          :value="status"
          @change="$emit('update:status', $event.target.value)"
          class="noc-filter-select"
        >
          <option value="">{{ t('audit_status_all') }}</option>
          <option value="SUCCESS">{{ t('audit_status_success') }}</option>
          <option value="FAILED">{{ t('audit_status_failed') }}</option>
          <option value="PENDING">Pending (PENDING)</option>
        </select>
      </div>

      <!-- 5. Custom Date Range -->
      <div class="noc-filter-col" title="Custom audit date range">
        <span class="noc-filter-label">{{ t('flt_date_range') }}</span>
        <div class="noc-date-range">
          <input
            id="audit-date-start"
            type="date"
            :value="startDate"
            @change="onDateChange($event.target.value, endDate)"
            title="Start Date"
          />
          <span class="text-gray-500">—</span>
          <input
            id="audit-date-end"
            type="date"
            :value="endDate"
            @change="onDateChange(startDate, $event.target.value)"
            title="End Date"
          />
        </div>
      </div>

      <!-- 6. Debounced Search Keyword -->
      <div class="noc-filter-col-search" title="Search operator, host, action, or parameters">
        <label class="noc-filter-label" for="audit-search-input">{{ t('flt_search') }}</label>
        <div class="noc-filter-search-box">
          <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            id="audit-search-input"
            :value="search"
            @input="$emit('update:search', $event.target.value)"
            type="search"
            placeholder="Search target, command, result..."
          />
        </div>
      </div>
    </template>

    <!-- Row 2: Quick Period Presets + Live Summary -->
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
  users: { type: Array, default: () => [] },
  servers: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  user: { type: String, default: '' },
  serverId: { type: String, default: '' },
  action: { type: String, default: '' },
  status: { type: String, default: '' },
  period: { type: String, default: '24h' },
  startDate: { type: String, default: '' },
  endDate: { type: String, default: '' },
  search: { type: String, default: '' },
  totalRows: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:user', 'update:serverId', 'update:action', 'update:status',
  'update:period', 'update:startDate', 'update:endDate', 'update:search', 'reset'
])

const presets = computed(() => [
  { val: 'all', label: t('audit_period_all') },
  { val: 'today', label: t('audit_period_today') },
  { val: '24h', label: t('audit_period_24h') },
  { val: '7d', label: t('audit_period_7d') },
  { val: '30d', label: t('audit_period_30d') },
])

const hasActiveFilters = computed(() => Boolean(
  props.user || props.serverId || props.action || props.status || props.startDate || props.endDate || props.search.trim() || props.period !== '24h'
))

const summaryLabel = computed(() => {
  if (props.startDate || props.endDate) return `${props.totalRows} activities (${props.startDate || '...'} to ${props.endDate || 'now'})`
  return `${props.totalRows} audit activities`
})

function selectPreset(val) {
  if (val !== 'custom') {
    emit('update:startDate', '')
    emit('update:endDate', '')
  }
  emit('update:period', val)
}

function onDateChange(s, e) {
  emit('update:startDate', s)
  emit('update:endDate', e)
  emit('update:period', (s || e) ? 'custom' : '24h')
}
</script>
