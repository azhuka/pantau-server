<template>
  <div class="hud-tactical-card rounded-xl p-4 space-y-3 font-mono">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>

    <NocFilterPanel
      :has-active-filters="Boolean(protoFilter || accessFilter || search.trim())"
      :summary-text="`${filteredPorts.length} of ${(ports || []).length} sockets`"
      compact
      @reset="protoFilter = ''; accessFilter = ''; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="port-proto-filter">{{ t('flt_protocol') }}</label>
          <select id="port-proto-filter" v-model="protoFilter" class="noc-filter-select">
            <option value="">{{ t('flt_all_protocols') }}</option>
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
        </div>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="port-access-filter">{{ t('flt_access') }}</label>
          <select id="port-access-filter" v-model="accessFilter" class="noc-filter-select">
            <option value="">{{ t('flt_all_access') }}</option>
            <option value="public">{{ t('flt_access_public') }}</option>
            <option value="local">{{ t('flt_access_local') }}</option>
          </select>
        </div>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="port-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="port-search-input" v-model="search" type="search" placeholder="Search port, bind IP, process..." />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="paginatedPorts.length === 0" class="text-xs text-gray-400 py-8 text-center">
      No listening sockets match the selected criteria.
    </div>
    <div v-else class="overflow-x-auto max-h-[460px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
          <tr class="text-gray-400 uppercase font-bold tracking-wider">
            <th class="py-2.5 px-3">{{ t('ws_col_port') || 'Port' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_proto') || 'Proto' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_bind') }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_service') }}</th>
            <th class="py-2.5 px-3 text-center">{{ t('ws_col_class') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(pt, idx) in paginatedPorts" :key="`${pt.proto}-${pt.port}-${idx}`" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 font-bold text-cyan-300">{{ pt.port }}</td>
            <td class="py-2.5 px-3 text-gray-400 uppercase">{{ pt.proto || 'tcp' }}</td>
            <td class="py-2.5 px-3 text-gray-300 font-semibold">{{ pt.ip || pt.bind || pt.address || '0.0.0.0' }}</td>
            <td class="py-2.5 px-3 text-gray-200">{{ pt.proc || pt.service || pt.program || pt.process || '-' }}</td>
            <td class="py-2.5 px-3 text-center">
              <span
                class="px-2 py-0.5 rounded text-[10px] font-bold"
                :class="isPublicPort(pt) ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'bg-cyan-950 text-cyan-300 border border-cyan-800'"
              >
                {{ isPublicPort(pt) ? 'PUBLIC' : 'INTERNAL' }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination
      v-model:page="currentPage"
      v-model:pageSize="pageSize"
      :total="filteredPorts.length"
      unitLabel="ports"
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
  ports: { type: Array, default: () => [] }
})

const protoFilter = ref('')
const accessFilter = ref('')
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

watch([protoFilter, accessFilter, search], () => { currentPage.value = 1 })

function isPublicPort(pt) {
  if (typeof pt.is_public === 'boolean') return pt.is_public
  const ip = String(pt.ip || pt.bind || pt.address || '')
  return !(pt.is_loopback || ip.startsWith('127.') || ip === '::1')
}

const filteredPorts = computed(() => {
  return (props.ports || []).filter(pt => {
    if (protoFilter.value && (pt.proto || '').toLowerCase() !== protoFilter.value) return false
    if (accessFilter.value === 'public' && !isPublicPort(pt)) return false
    if (accessFilter.value === 'local' && isPublicPort(pt)) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = `${pt.proto || ''} ${pt.port || ''} ${pt.ip || pt.bind || ''} ${pt.proc || pt.service || pt.process || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const paginatedPorts = computed(() => {
  if (pageSize.value === 'all') return filteredPorts.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return filteredPorts.value.slice(start, start + limit)
})
</script>
