<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-[11px]">
        <button
          v-for="f in filters"
          :key="f.id"
          type="button"
          @click="category = f.id"
          class="px-2.5 py-1 rounded transition cursor-pointer"
          :class="category === f.id ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'"
        >
          {{ f.label }}
        </button>
      </div>
      <div class="noc-filter-search-box">
        <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input v-model="search" type="search" placeholder="Search group name or member..." />
      </div>
    </div>

    <div v-if="paginatedGroups.length === 0" class="text-xs text-gray-400 py-8 text-center">
      No system groups match the selected criteria.
    </div>
    <div v-else class="overflow-x-auto max-h-[380px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2 px-3">{{ t('ws_col_group_name') }}</th>
            <th class="py-2 px-3">{{ t('ws_col_gid') }}</th>
            <th class="py-2 px-3 text-center">{{ t('ws_col_type') }}</th>
            <th class="py-2 px-3">{{ t('ws_col_members') }}</th>
            <th class="py-2 px-3 text-center">{{ t('ws_col_count') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(g, idx) in paginatedGroups" :key="`${g.group}-${idx}`" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 font-semibold text-gray-200 whitespace-nowrap">
              <span>{{ g.group }}</span>
              <span v-if="g.is_privileged" class="ml-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">Privileged</span>
            </td>
            <td class="py-2 px-3 text-gray-400">{{ g.gid ?? '-' }}</td>
            <td class="py-2 px-3 text-center">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="g.is_system ? 'bg-gray-800 text-gray-400 border border-gray-700' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'">
                {{ g.is_system ? 'System' : 'Regular' }}
              </span>
            </td>
            <td class="py-2 px-3">
              <div v-if="(g.members || []).length > 0" class="flex items-center gap-1 flex-wrap">
                <span v-for="m in g.members.slice(0, 8)" :key="m" class="px-1.5 py-0.5 rounded bg-gray-900 border border-gray-800 text-[10px] text-gray-300">{{ m }}</span>
                <span v-if="g.members.length > 8" class="px-1.5 py-0.5 rounded bg-cyan-950/60 text-cyan-300 text-[10px]" :title="g.members.join(', ')">+{{ g.members.length - 8 }}</span>
              </div>
              <span v-else class="text-gray-500">-</span>
            </td>
            <td class="py-2 px-3 text-center font-bold text-gray-300">{{ g.member_count ?? (g.members || []).length }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredGroups.length" unitLabel="groups" :pageSizeOptions="[10, 25, 50, 'all']" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  groups: { type: Array, default: () => [] },
})

const filters = [
  { id: 'all', label: 'All' },
  { id: 'regular', label: 'Regular' },
  { id: 'system', label: 'System' },
  { id: 'privileged', label: 'Privileged' },
]

const category = ref('all')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

watch([category, search], () => { currentPage.value = 1 })

const filteredGroups = computed(() => {
  return (props.groups || []).filter(g => {
    if (category.value === 'regular' && g.is_system) return false
    if (category.value === 'system' && !g.is_system) return false
    if (category.value === 'privileged' && !g.is_privileged) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = `${g.group || ''} ${g.gid ?? ''} ${(g.members || []).join(' ')}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const paginatedGroups = computed(() => {
  if (pageSize.value === 'all') return filteredGroups.value
  const lim = parseInt(pageSize.value, 10) || 10
  return filteredGroups.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})
</script>
