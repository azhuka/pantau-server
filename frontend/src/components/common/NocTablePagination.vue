<template>
  <div
    v-if="shouldShow"
    class="table-pagination-bar px-4 py-2.5 border-t border-gray-800 bg-[#070c18]/90 flex items-center justify-between text-xs text-gray-400 font-mono select-none flex-wrap gap-3"
  >
    <!-- 1. LEFT: Showing Start–End of Total Unit -->
    <div class="table-pagination-info text-[11.5px] text-gray-400">
      Showing {{ total === 0 ? 0 : startIdx + 1 }}–{{ endIdx }} of {{ total }} {{ unitLabel }}
    </div>

    <!-- 2. CENTER: Prev, Page X of Y, Next -->
    <div class="table-pagination-nav flex items-center gap-2">
      <button
        type="button"
        :disabled="page <= 1"
        @click="setPage(page - 1)"
        class="btn-pg px-2.5 py-1 rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700 disabled:opacity-35 disabled:cursor-not-allowed transition cursor-pointer text-[11.5px] font-medium"
      >
        « Previous
      </button>
      <span class="page-indicator font-semibold text-gray-200 text-[11.5px] px-1">
        Page {{ page }} of {{ totalPages }}
      </span>
      <button
        type="button"
        :disabled="page >= totalPages"
        @click="setPage(page + 1)"
        class="btn-pg px-2.5 py-1 rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700 disabled:opacity-35 disabled:cursor-not-allowed transition cursor-pointer text-[11.5px] font-medium"
      >
        Next »
      </button>
    </div>

    <!-- 3. RIGHT: Show: [ 10 Unit ▾ ] -->
    <div class="table-pagination-limit flex items-center gap-2 text-[11.5px]">
      <span>Show:</span>
      <select
        :value="pageSize"
        @change="onSizeChange($event.target.value)"
        class="bg-[#0b1322] border border-gray-700 rounded px-2 py-0.5 text-gray-200 cursor-pointer text-[11.5px] focus:outline-none focus:border-cyan-500 font-mono"
      >
        <option v-for="opt in pageSizeOptions" :key="opt" :value="opt">
          {{ opt === 'all' ? 'All ' + unitLabel : opt + ' ' + unitLabel }}
        </option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'

const props = defineProps({
  total: { type: Number, required: true },
  page: { type: Number, default: 1 },
  pageSize: { type: [Number, String], default: 10 },
  pageSizeOptions: { type: Array, default: () => [10, 25, 50, 100, 'all'] },
  unitLabel: { type: String, default: 'rows' },
  alwaysShow: { type: Boolean, default: false },
})

const emit = defineEmits(['update:page', 'update:pageSize'])

const minPageLimit = computed(() => {
  if (Array.isArray(props.pageSizeOptions) && props.pageSizeOptions.length) {
    const first = parseInt(props.pageSizeOptions[0], 10)
    return isNaN(first) ? 10 : first
  }
  return 10
})

const shouldShow = computed(() => {
  if (props.alwaysShow) return props.total > 0
  return props.total > minPageLimit.value
})

const limit = computed(() => {
  if (props.pageSize === 'all') return props.total || 1
  return parseInt(props.pageSize, 10) || 10
})

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / (limit.value || 1))))

const startIdx = computed(() => (props.pageSize === 'all' ? 0 : (props.page - 1) * limit.value))
const endIdx = computed(() => (props.pageSize === 'all' ? props.total : Math.min(startIdx.value + limit.value, props.total)))

function setPage(p) {
  const target = Math.max(1, Math.min(p, totalPages.value))
  emit('update:page', target)
}

function onSizeChange(val) {
  const newSize = val === 'all' ? 'all' : parseInt(val, 10)
  emit('update:pageSize', newSize)
  emit('update:page', 1)
}

watch(totalPages, (newMax) => {
  if (props.page > newMax) {
    emit('update:page', newMax)
  }
})
</script>
