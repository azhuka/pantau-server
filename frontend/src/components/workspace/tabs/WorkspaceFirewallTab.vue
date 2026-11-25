<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-4">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-cyan-500/20">
      <div class="flex items-center gap-2">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_fw_title') }}</h3>
        <span class="px-2 py-0.5 rounded text-[11px] uppercase font-bold" :class="firewallData?.status === 'active' ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60' : 'bg-gray-800 text-gray-400 border border-gray-700'">
          {{ firewallData?.status || 'unknown' }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button type="button" @click="toggleUfw" class="px-2.5 py-1 rounded text-xs font-bold transition cursor-pointer flex items-center gap-1.5" :class="firewallData?.status === 'active' ? 'bg-rose-950 text-rose-300 border border-rose-800 hover:bg-rose-900' : 'bg-emerald-950 text-emerald-300 border border-emerald-800 hover:bg-emerald-900'">
          <span>{{ firewallData?.status === 'active' ? 'Disable UFW' : 'Enable UFW' }}</span>
        </button>
        <button type="button" @click="$emit('firewall-action', { action: 'ufw_reload', params: {} })" class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 hover:bg-cyan-900 text-xs font-bold transition cursor-pointer" title="Reload UFW firewall rules">
          <span>Reload</span>
        </button>
      </div>
    </div>

    <div class="p-3 rounded-lg bg-[#070c18] border border-cyan-900/40 space-y-2">
      <div class="text-[11px] font-bold text-gray-300 uppercase">// Manual IP Blocklist</div>
      <form @submit.prevent="submitBlockIp" class="flex items-center gap-2 flex-wrap">
        <input v-model="blockIpInput" type="text" placeholder="IP Address (e.g. 192.168.1.50 or 10.0.0.0/24)" required class="bg-[#0b1326] border border-gray-800 focus:border-rose-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none flex-1 min-w-[200px]" />
        <input v-model="blockCommentInput" type="text" placeholder="Comment (optional, e.g. SSH brute force)" class="bg-[#0b1326] border border-gray-800 focus:border-rose-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none w-48" />
        <button type="submit" class="px-3 py-1.5 rounded bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-bold transition cursor-pointer flex items-center gap-1.5">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
          <span>Block IP</span>
        </button>
      </form>
    </div>

    <NocFilterPanel
      v-if="rawRules.length > 0"
      :has-active-filters="Boolean(actionFilter || search.trim())"
      :summary-text="`${filteredRules.length} of ${rawRules.length} rules`"
      compact
      @reset="actionFilter = ''; search = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="fw-act-filter">{{ t('ws_col_action') }}</label>
          <select id="fw-act-filter" v-model="actionFilter" class="noc-filter-select">
            <option value="">All Actions</option>
            <option value="ALLOW">ALLOW</option>
            <option value="DENY">DENY / REJECT</option>
          </select>
        </div>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="fw-search-input">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="fw-search-input" v-model="search" type="search" placeholder="Search port, IP, rule..." />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="rawRules.length === 0" class="text-xs text-gray-400 py-8 text-center">
      {{ t('ws_fw_empty') || 'No active firewall rules configured.' }}
    </div>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
          <tr>
            <th class="py-2.5 px-3">{{ t('ws_col_to') || 'To (Port/Service)' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_action') || 'Action' }}</th>
            <th class="py-2.5 px-3">{{ t('ws_col_from') || 'From (Source)' }}</th>
            <th class="py-2.5 px-3 text-right">{{ t('col_actions') || 'Actions' }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(r, idx) in filteredRules" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2.5 px-3 font-semibold text-gray-200">{{ typeof r === 'string' ? r : (r.to || r.target) }}</td>
            <td class="py-2.5 px-3">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold" :class="isDenyRule(r) ? 'bg-rose-950 text-rose-300 border border-rose-700' : 'bg-emerald-950 text-emerald-300 border border-emerald-700'">
                {{ typeof r === 'string' ? (isDenyRule(r) ? 'DENY' : 'ALLOW') : (r.action || 'ALLOW') }}
              </span>
            </td>
            <td class="py-2.5 px-3 text-gray-400">{{ typeof r === 'string' ? '-' : (r.from || 'Anywhere') }}</td>
            <td class="py-2.5 px-3 text-right">
              <button v-if="typeof r === 'object' && r.from && r.from !== 'Anywhere' && isDenyRule(r)" type="button" @click="$emit('firewall-action', { action: 'unblock_ip', params: { ip: r.from } })" class="px-2 py-0.5 rounded bg-gray-900 hover:bg-emerald-950 border border-gray-700 text-gray-300 hover:text-emerald-300 text-[11px] font-bold transition cursor-pointer" title="Unblock IP from UFW">
                Unblock
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../../i18n'
import NocFilterPanel from '../../common/NocFilterPanel.vue'

const { t } = useI18n()

const props = defineProps({
  firewallData: { type: Object, default: () => ({ status: 'unknown', rules: [] }) }
})

const emit = defineEmits(['firewall-action'])
const blockIpInput = ref('')
const blockCommentInput = ref('')
const actionFilter = ref('')
const search = ref('')

const rawRules = computed(() => {
  const r = props.firewallData?.rules
  if (Array.isArray(r)) return r
  if (typeof r === 'string') { try { const p = JSON.parse(r); return Array.isArray(p) ? p : [] } catch { return [] } }
  return []
})

function isDenyRule(r) {
  const act = typeof r === 'string' ? r.toUpperCase() : String(r.action || 'ALLOW').toUpperCase()
  return act.includes('DENY') || act.includes('REJECT') || act.includes('DROP')
}

const filteredRules = computed(() => {
  return rawRules.value.filter(r => {
    if (actionFilter.value === 'ALLOW' && isDenyRule(r)) return false
    if (actionFilter.value === 'DENY' && !isDenyRule(r)) return false
    if (search.value.trim()) {
      const q = search.value.toLowerCase()
      const hay = typeof r === 'string' ? r.toLowerCase() : `${r.to || r.target || ''} ${r.action || ''} ${r.from || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

function toggleUfw() {
  const st = props.firewallData?.status
  const next = st === 'active' ? 'ufw_disable' : 'ufw_enable'
  if (!confirm(st === 'active' ? 'Are you sure you want to DISABLE UFW firewall?' : 'Are you sure you want to ENABLE UFW firewall?')) return
  emit('firewall-action', { action: next, params: {} })
}

function submitBlockIp() {
  if (!blockIpInput.value.trim()) return
  emit('firewall-action', { action: 'block_ip', params: { ip: blockIpInput.value.trim(), comment: blockCommentInput.value.trim() } })
  blockIpInput.value = ''; blockCommentInput.value = ''
}
</script>
