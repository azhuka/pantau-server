<template>
  <div class="relative font-mono" ref="dropdownRef">
    <!-- Toggle Button -->
    <button
      type="button"
      @click="isOpen = !isOpen"
      :class="[
        'px-2.5 py-1 rounded text-xs transition cursor-pointer flex items-center gap-1.5 border font-semibold select-none',
        isOpen || hiddenCount > 0
          ? 'bg-cyan-950 text-cyan-300 border-cyan-500/50 shadow-[0_0_8px_rgba(56,189,248,0.2)]'
          : 'bg-[#060a14] border-cyan-900/40 text-gray-300 hover:text-cyan-200 hover:border-cyan-700/60'
      ]"
      :title="t('col_customizer_title')"
    >
      <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <line x1="9" y1="3" x2="9" y2="21"/>
        <line x1="15" y1="3" x2="15" y2="21"/>
      </svg>
      <span>{{ t('col_customizer_btn') }}</span>
      <span class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/50">
        {{ visibleCount }}/{{ columns.length }}
      </span>
      <svg class="w-3 h-3 text-gray-400 transition-transform" :class="{ 'rotate-180 text-cyan-400': isOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>

    <!-- Dropdown Menu -->
    <div
      v-if="isOpen"
      class="absolute right-0 top-full mt-1.5 w-64 bg-[#080d19]/95 border border-cyan-500/40 rounded-xl shadow-[0_12px_36px_rgba(0,0,0,0.85)] backdrop-blur-md z-50 p-2.5 select-none text-xs"
    >
      <!-- Header with Title and Reset -->
      <div class="flex items-center justify-between pb-2 border-b border-cyan-900/40 mb-2">
        <div class="flex items-center gap-1.5 text-gray-200 font-bold uppercase tracking-wider text-[11px]">
          <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
          <span>{{ t('col_customizer_title') }}</span>
        </div>
        <button
          type="button"
          @click="resetColumns"
          class="text-[10px] font-bold text-gray-400 hover:text-cyan-300 transition cursor-pointer underline hover:no-underline"
          :title="t('col_customizer_reset')"
        >
          {{ t('col_customizer_reset') }}
        </button>
      </div>

      <!-- Quick Presets -->
      <div class="mb-2.5">
        <div class="text-[10px] text-gray-400 font-bold uppercase mb-1">
          {{ t('col_customizer_presets') }}:
        </div>
        <div class="grid grid-cols-3 gap-1">
          <button
            type="button"
            @click="applyPreset('all')"
            class="px-1.5 py-0.8 rounded text-[10px] font-bold text-center bg-[#0d1627] hover:bg-cyan-950/70 text-gray-300 hover:text-cyan-200 border border-cyan-900/40 transition cursor-pointer"
          >
            {{ t('col_preset_all') }}
          </button>
          <button
            type="button"
            @click="applyPreset('perf')"
            class="px-1.5 py-0.8 rounded text-[10px] font-bold text-center bg-[#0d1627] hover:bg-cyan-950/70 text-gray-300 hover:text-cyan-200 border border-cyan-900/40 transition cursor-pointer"
          >
            {{ t('col_preset_perf') }}
          </button>
          <button
            type="button"
            @click="applyPreset('inventory')"
            class="px-1.5 py-0.8 rounded text-[10px] font-bold text-center bg-[#0d1627] hover:bg-cyan-950/70 text-gray-300 hover:text-cyan-200 border border-cyan-900/40 transition cursor-pointer"
          >
            {{ t('col_preset_inventory') }}
          </button>
        </div>
      </div>

      <!-- Columns Checklist -->
      <div class="space-y-1 max-h-[350px] overflow-y-auto pr-0.5 custom-scrollbar">
        <label
          v-for="col in columns"
          :key="col.id"
          :class="[
            'flex items-center justify-between px-2 py-1 rounded transition text-xs select-none',
            col.locked ? 'opacity-70 cursor-not-allowed bg-black/20' : 'hover:bg-cyan-950/40 cursor-pointer'
          ]"
        >
          <div class="flex items-center gap-2">
            <input
              type="checkbox"
              :checked="col.visible"
              :disabled="col.locked"
              @change="toggleCol(col.id, $event.target.checked)"
              class="rounded bg-black/40 border-gray-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 cursor-pointer disabled:cursor-not-allowed accent-cyan-400"
            />
            <span :class="col.visible ? 'text-gray-200 font-medium' : 'text-gray-500'">
              {{ col.label }}
            </span>
          </div>

          <span v-if="col.locked" class="text-[9px] font-bold text-cyan-400/80 uppercase flex items-center gap-1">
            <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <span>{{ t('col_locked') }}</span>
          </span>
        </label>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'

const props = defineProps({
  columns: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['toggle', 'preset', 'reset'])

const { t } = useI18n()
const isOpen = ref(false)
const dropdownRef = ref(null)

const visibleCount = computed(() => props.columns.filter(c => c.visible).length)
const hiddenCount = computed(() => props.columns.filter(c => !c.visible).length)

function toggleCol(colId, visible) {
  emit('toggle', colId, visible)
}

function applyPreset(presetName) {
  emit('preset', presetName)
}

function resetColumns() {
  emit('reset')
}

function handleClickOutside(e) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target)) {
    isOpen.value = false
  }
}

function handleKeydown(e) {
  if (e.key === 'Escape') {
    isOpen.value = false
  }
}

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
  window.removeEventListener('keydown', handleKeydown)
})
</script>
