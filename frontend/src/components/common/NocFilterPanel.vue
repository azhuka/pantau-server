<template>
  <div class="noc-filter-panel font-mono select-none" :class="{ 'is-compact': compact }">
    <!-- Primary Filter Row: Fields (left) + Actions (right, bottom-aligned) -->
    <div class="noc-filter-row-main">
      <div class="noc-filter-fields">
        <slot name="fields" />
      </div>

      <div class="noc-filter-actions">
        <button
          v-if="hasActiveFilters"
          type="button"
          class="noc-btn-toolbar text-amber-300 border-amber-700/50 hover:border-amber-400"
          :title="resetTitle"
          @click="$emit('reset')"
        >
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
            <path d="M3 3v5h5" />
          </svg>
          <span>Reset</span>
        </button>

        <slot name="actions" />

        <span v-if="summaryText && !$slots.sub" class="text-[11.5px] text-gray-400 whitespace-nowrap">
          {{ summaryText }}
        </span>
      </div>
    </div>

    <!-- Optional Secondary Row: Quick Presets & Summary Info -->
    <template v-if="$slots.sub">
      <div class="noc-filter-divider"></div>
      <div class="noc-filter-sub">
        <div class="flex items-center gap-2 flex-wrap">
          <slot name="sub" />
        </div>
        <div v-if="summaryText" class="text-[11.5px] text-gray-400 whitespace-nowrap">
          {{ summaryText }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
defineProps({
  hasActiveFilters: { type: Boolean, default: false },
  summaryText: { type: String, default: '' },
  resetTitle: { type: String, default: 'Reset all filters to default' },
  compact: { type: Boolean, default: false },
})

defineEmits(['reset'])
</script>
