<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2 flex-wrap gap-2">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">SSL/TLS Certificate Tracking</h3>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="certificates.length > 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-gray-800 text-gray-400'">
            {{ certificates.length }} discovered
          </span>
        </div>
        <p class="text-[11px] text-gray-400 mt-0.5">HTTPS certificate expiry monitoring (Let's Encrypt &amp; custom paths)</p>
      </div>

      <button
        v-if="!isViewer"
        type="button"
        :disabled="!isOnline"
        @click="showAddForm = !showAddForm"
        class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-600/50 hover:bg-cyan-900 transition cursor-pointer text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed"
        :title="isOnline ? 'Add custom SSL certificate directory or file path' : 'Server offline — action disabled'"
      >
        + Add Cert Path
      </button>
    </div>

    <form v-if="showAddForm && !isViewer" @submit.prevent="submitAddSslPath" class="flex items-center gap-2 flex-wrap p-2.5 rounded-lg bg-[#060a14] border border-cyan-800/50 text-xs">
      <input v-model="newPath" type="text" required placeholder="Certificate path (e.g. /etc/nginx/ssl)" class="flex-1 min-w-[240px] px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
      <button type="submit" :disabled="!isOnline" class="px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer disabled:opacity-50">Save</button>
      <button type="button" @click="showAddForm = false" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
    </form>

    <div v-if="certificates.length === 0" class="text-xs text-gray-400 py-8 text-center">
      <div>{{ t('ssl_empty_desc') }}</div>
      <div class="text-[11px] text-gray-500 mt-1">{{ t('ssl_empty_hint') }}</div>
    </div>

    <div v-else class="overflow-x-auto max-h-[420px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2 px-3">{{ t('ssl_col_domain') }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_issuer') }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_expires') }}</th>
            <th class="py-2 px-3 text-center">{{ t('ssl_col_days_left') }}</th>
            <th class="py-2 px-3 text-center">{{ t('ssl_col_status') }}</th>
            <th class="py-2 px-3">{{ t('ssl_col_file_path') }}</th>
            <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(c, idx) in paginatedCerts" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 text-cyan-300 font-bold">
              <span>{{ formatDomain(c) }}</span>
              <span v-if="c.is_custom" class="ml-1.5 px-1.5 py-0.5 rounded text-[9px] bg-cyan-950 text-cyan-300 border border-cyan-800">Custom</span>
            </td>
            <td class="py-2 px-3 text-gray-300 truncate max-w-[180px]" :title="c.issuer || ''">{{ formatIssuer(c.issuer) }}</td>
            <td class="py-2 px-3 text-gray-400 whitespace-nowrap">{{ formatExpiry(c.not_after || c.expires) }}</td>
            <td class="py-2 px-3 text-center font-bold whitespace-nowrap" :class="daysClass(c)">
              {{ c.is_expired ? 'Expired' : (c.days_left !== undefined && c.days_left !== null ? `${c.days_left}d` : '-') }}
            </td>
            <td class="py-2 px-3 text-center">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold border" :class="statusBadgeClass(c)">
                {{ statusLabel(c) }}
              </span>
            </td>
            <td class="py-2 px-3 text-gray-400 text-[11px] truncate max-w-[200px]" :title="c.path || ''">{{ c.path || '-' }}</td>
            <td class="py-2 px-3 text-center">
              <button
                v-if="c.is_custom && !isViewer"
                type="button"
                :disabled="!isOnline"
                @click="$emit('ssl-action', { action: 'ssl_path_remove', params: { path: c.path } })"
                class="px-2 py-0.5 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700/60 text-rose-300 text-[11px] font-bold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Remove
              </button>
              <span v-else class="text-gray-500 text-[11px]">System</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="certificates.length" unitLabel="certificates" :pageSizeOptions="[10, 25, 50, 'all']" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../../i18n'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  sslCertsList: { type: Array, default: () => [] },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})

const emit = defineEmits(['ssl-action'])

const showAddForm = ref(false)
const newPath = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const certificates = computed(() => Array.isArray(props.sslCertsList) ? props.sslCertsList : [])

const paginatedCerts = computed(() => {
  if (pageSize.value === 'all') return certificates.value
  const lim = parseInt(pageSize.value, 10) || 10
  return certificates.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})

function formatDomain(c) {
  if (Array.isArray(c.domains) && c.domains.length) return c.domains.join(', ')
  return c.subject || c.domain || '-'
}

function formatIssuer(iss) {
  const s = String(iss || '-')
  const m = s.match(/(?:commonName|CN|organizationName|O)=([^/,]+)/)
  return m ? m[1].trim() : s
}

function formatExpiry(dt) {
  if (!dt) return '-'
  return String(dt).replace('T', ' ').slice(0, 16)
}

function daysClass(c) {
  if (c.is_expired || c.is_critical || Number(c.days_left) <= 7) return 'text-rose-400'
  if (c.is_warning || Number(c.days_left) <= 30) return 'text-amber-300'
  return 'text-emerald-400'
}

function statusLabel(c) {
  if (c.is_expired) return 'EXPIRED'
  if (c.is_critical || Number(c.days_left) <= 7) return 'CRITICAL'
  if (c.is_warning || Number(c.days_left) <= 30) return 'WARNING'
  return 'VALID'
}

function statusBadgeClass(c) {
  const st = statusLabel(c)
  if (st === 'EXPIRED' || st === 'CRITICAL') return 'bg-rose-950 text-rose-300 border-rose-700'
  if (st === 'WARNING') return 'bg-amber-950 text-amber-300 border-amber-700'
  return 'bg-emerald-950 text-emerald-300 border-emerald-700'
}

function submitAddSslPath() {
  const p = newPath.value.trim()
  if (!p) return
  emit('ssl-action', { action: 'ssl_path_add', params: { path: p } })
  newPath.value = ''
  showAddForm.value = false
}
</script>
