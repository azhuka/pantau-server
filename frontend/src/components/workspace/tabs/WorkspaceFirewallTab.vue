<template>
  <div class="space-y-4 font-mono">
    <!-- Card 1: Firewall Status, KPIs & Rules -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-4">
      <div class="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-cyan-500/20">
        <div>
          <div class="flex items-center gap-2">
            <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">{{ t('ws_fw_title') }}</h3>
            <span class="px-2 py-0.5 rounded text-[10px] uppercase font-bold" :class="isActive ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60' : 'bg-amber-950 text-amber-300 border border-amber-700/60'">
              {{ isActive ? 'ACTIVE (PROTECTING)' : 'INACTIVE (OPEN)' }}
            </span>
          </div>
          <p class="text-[11px] text-gray-400 mt-0.5">Host network packet filtering and inbound/outbound port policy</p>
        </div>

        <div v-if="!isViewer" class="flex items-center gap-2 flex-wrap">
          <template v-if="isActive">
            <button
              type="button"
              :disabled="!isOnline || busy"
              @click="$emit('firewall-action', { action: 'firewall_reload', params: {} })"
              class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 hover:bg-cyan-900 text-xs font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="busy ? 'Applying firewall command...' : (isOnline ? 'Reload firewall rules without dropping active connections' : 'Server offline — action disabled')"
            >
              {{ busy ? 'Processing...' : 'Reload Rules' }}
            </button>
            <button
              type="button"
              :disabled="!isOnline || busy"
              @click="toggleUfw"
              class="px-2.5 py-1 rounded bg-amber-950 text-amber-300 border border-amber-700/60 hover:bg-amber-900 text-xs font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              :title="busy ? 'Applying firewall command...' : (isOnline ? 'Disable UFW firewall' : 'Server offline — action disabled')"
            >
              {{ busy ? 'Processing...' : 'Disable Firewall' }}
            </button>
          </template>
          <button
            v-else
            type="button"
            :disabled="!isOnline || busy"
            @click="toggleUfw"
            class="px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-700/60 hover:bg-emerald-900 text-xs font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="busy ? 'Applying firewall command...' : (isOnline ? 'Enable UFW firewall (auto-allows SSH & port 8400)' : 'Server offline — action disabled')"
          >
            {{ busy ? 'Enabling...' : 'Enable Firewall' }}
          </button>
        </div>
      </div>

      <!-- 3 Summary KPI Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div class="p-3 rounded-lg bg-[#060a14] border-l-2" :class="isActive ? 'border-emerald-500' : 'border-amber-500'">
          <div class="text-[10px] uppercase text-gray-400 font-bold">Firewall Status</div>
          <div class="text-base font-bold mt-0.5" :class="isActive ? 'text-emerald-400' : 'text-amber-400'">
            {{ (firewallData?.status || 'unknown').toUpperCase() }}
          </div>
        </div>
        <div class="p-3 rounded-lg bg-[#060a14] border-l-2 border-cyan-500">
          <div class="text-[10px] uppercase text-gray-400 font-bold">Backend</div>
          <div class="text-base font-bold text-gray-100 mt-0.5">
            {{ (firewallData?.backend || 'ufw').toUpperCase() }}
          </div>
        </div>
        <div class="p-3 rounded-lg bg-[#060a14] border-l-2 border-rose-500">
          <div class="text-[10px] uppercase text-gray-400 font-bold">Blocked IPs (DROP)</div>
          <div class="text-base font-bold text-rose-400 mt-0.5">
            {{ blockedIps.length }} IPs
          </div>
        </div>
      </div>

      <!-- Port Rule Quick Form + Firewall Rules Table -->
      <div class="space-y-2.5">
        <h4 class="text-[11px] font-bold text-gray-300 uppercase tracking-wider">Firewall Rules &amp; Port Policies ({{ rawRules.length }})</h4>

        <form v-if="!isViewer" @submit.prevent="submitPortRule('allow')" class="flex items-center gap-2 flex-wrap p-2.5 rounded-lg bg-[#060a14] border border-cyan-900/40">
          <input v-model.number="portInput" type="number" min="1" max="65535" placeholder="Port (e.g. 443)" required class="bg-[#0b1326] border border-gray-800 focus:border-cyan-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none w-36" />
          <select v-model="portProto" class="bg-[#0b1326] border border-gray-800 focus:border-cyan-500 rounded px-2.5 py-1.5 text-xs text-gray-200 outline-none">
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
          <button
            type="submit"
            :disabled="!isOnline || busy"
            class="px-3 py-1.5 rounded bg-emerald-950 hover:bg-emerald-900 border border-emerald-800 text-emerald-300 text-xs font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? 'Allow inbound traffic on this port' : 'Server offline — action disabled'"
          >
            Allow Port
          </button>
          <button
            type="button"
            :disabled="!isOnline || busy"
            @click="submitPortRule('deny')"
            class="px-3 py-1.5 rounded bg-amber-950 hover:bg-amber-900 border border-amber-800 text-amber-300 text-xs font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? 'Block inbound traffic on this port (ports 22 & 8400 protected)' : 'Server offline — action disabled'"
          >
            Block Port
          </button>
        </form>

        <div v-if="rawRules.length === 0" class="text-xs text-gray-400 py-6 text-center bg-[#060a14] rounded-lg border border-gray-800/60">
          {{ isActive ? 'No explicit rules configured (using default backend policy).' : 'Firewall is currently inactive. Ports are unfiltered.' }}
        </div>
        <div v-else class="overflow-x-auto max-h-[300px]">
          <table class="w-full text-left text-xs border-collapse">
            <thead class="sticky top-0 bg-[#070c18] border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
              <tr>
                <th class="py-2 px-3 w-12">#</th>
                <th class="py-2 px-3">{{ t('ws_col_action') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-800/40">
              <tr v-for="(r, idx) in paginatedRules" :key="idx" class="hover:bg-cyan-950/20">
                <td class="py-2 px-3 text-gray-500">{{ (rulesPage - 1) * 10 + idx + 1 }}</td>
                <td class="py-2 px-3 text-gray-200">{{ typeof r === 'string' ? r : `${r.to || r.target || '-'} — ${r.action || 'ALLOW'} (${r.from || 'Anywhere'})` }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <NocTablePagination v-model:page="rulesPage" v-model:pageSize="rulesPageSize" :total="rawRules.length" unitLabel="rules" :pageSizeOptions="[10, 25, 50, 'all']" />
      </div>
    </div>

    <!-- Card 2: Blocked IP Blacklist (iptables DROP) -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 class="text-xs font-bold text-rose-400 uppercase tracking-wider">Blocked IP Blacklist (iptables DROP)</h3>
          <p class="text-[11px] text-gray-400">Source IPv4 addresses actively dropped on the host INPUT chain</p>
        </div>
      </div>

      <form v-if="!isViewer" @submit.prevent="submitBlockIp" class="flex items-center gap-2 flex-wrap p-2.5 rounded-lg bg-[#060a14] border border-cyan-900/40">
        <input v-model="blockIpInput" type="text" placeholder="IPv4 Address (e.g. 192.168.1.50)" required class="bg-[#0b1326] border border-gray-800 focus:border-rose-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none flex-1 min-w-[200px]" />
        <input v-model="blockCommentInput" type="text" placeholder="Reason (optional)" class="bg-[#0b1326] border border-gray-800 focus:border-rose-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none w-48" />
        <button
          type="submit"
          :disabled="!isOnline"
          class="px-3 py-1.5 rounded bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-bold transition cursor-pointer inline-flex items-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
          :title="isOnline ? 'Block IPv4 address via iptables DROP' : 'Server offline — action disabled'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
          <span>Block IP</span>
        </button>
      </form>

      <div v-if="blockedIps.length === 0" class="text-xs text-gray-400 py-6 text-center">
        No source IPs are currently blocked on the iptables INPUT chain.
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
            <tr>
              <th class="py-2 px-3 w-14 text-center">#</th>
              <th class="py-2 px-3">{{ t('ws_col_from') }}</th>
              <th class="py-2 px-3 text-right">Packets</th>
              <th class="py-2 px-3 text-right">Bytes</th>
              <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr v-for="(b, idx) in paginatedBlocked" :key="`${b.source}-${idx}`" class="hover:bg-cyan-950/20">
              <td class="py-2 px-3 text-center text-gray-500">{{ b.num || idx + 1 }}</td>
              <td class="py-2 px-3 font-bold text-rose-400">
                <button type="button" @click="copyIp(b.source)" class="hover:underline cursor-pointer" :title="copiedIp === b.source ? 'Copied!' : 'Click to copy IP'">
                  {{ b.source }}
                </button>
              </td>
              <td class="py-2 px-3 text-right text-gray-300">{{ b.pkts ?? 0 }}</td>
              <td class="py-2 px-3 text-right text-gray-300">{{ b.bytes ?? 0 }}</td>
              <td class="py-2 px-3 text-center">
                <button
                  v-if="!isViewer"
                  type="button"
                  :disabled="!isOnline"
                  @click="unblockIp(b.source)"
                  class="px-2 py-0.5 rounded bg-emerald-950/60 hover:bg-emerald-900 border border-emerald-700/60 text-emerald-300 text-[11px] font-bold transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  :title="isOnline ? `Remove DROP rule for ${b.source}` : 'Server offline — action disabled'"
                >
                  Unblock
                </button>
                <span v-else class="text-gray-500 text-[11px]">Read-Only</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination v-model:page="blockedPage" v-model:pageSize="blockedPageSize" :total="blockedIps.length" unitLabel="IPs" :pageSizeOptions="[10, 25, 50, 'all']" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from '../../../i18n'
import { confirmAction } from '../../../utils/useToast'
import NocTablePagination from '../../common/NocTablePagination.vue'

const { t } = useI18n()

const props = defineProps({
  firewallData: { type: Object, default: () => ({ status: 'unknown', backend: 'ufw', rules: [], blocked_ips: [] }) },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['firewall-action'])

const blockIpInput = ref('')
const blockCommentInput = ref('')
const portInput = ref('')
const portProto = ref('tcp')
const copiedIp = ref('')
const rulesPage = ref(1)
const rulesPageSize = ref(10)
const blockedPage = ref(1)
const blockedPageSize = ref(10)

const isActive = computed(() => String(props.firewallData?.status || '').toLowerCase() === 'active')

const rawRules = computed(() => {
  const r = props.firewallData?.rules
  if (Array.isArray(r)) return r
  if (typeof r === 'string') { try { const p = JSON.parse(r); return Array.isArray(p) ? p : [] } catch { return [] } }
  return []
})

const blockedIps = computed(() => {
  const b = props.firewallData?.blocked_ips
  return Array.isArray(b) ? b : []
})

const paginatedRules = computed(() => {
  if (rulesPageSize.value === 'all') return rawRules.value
  const lim = parseInt(rulesPageSize.value, 10) || 10
  return rawRules.value.slice((rulesPage.value - 1) * lim, rulesPage.value * lim)
})

const paginatedBlocked = computed(() => {
  if (blockedPageSize.value === 'all') return blockedIps.value
  const lim = parseInt(blockedPageSize.value, 10) || 10
  return blockedIps.value.slice((blockedPage.value - 1) * lim, blockedPage.value * lim)
})

async function toggleUfw() {
  const next = isActive.value ? 'firewall_disable' : 'firewall_enable'
  const ok = await confirmAction({
    title: isActive.value ? 'Disable UFW Firewall' : 'Enable UFW Firewall',
    message: isActive.value
      ? 'Disable UFW firewall on target host? Inbound ports will become unfiltered.'
      : 'Enable UFW firewall? SSH (22) and Pantau management port (8400) will be auto-allowed.',
    confirmText: isActive.value ? 'Disable Firewall' : 'Enable Firewall',
    variant: isActive.value ? 'danger' : 'primary',
  })
  if (!ok) return
  emit('firewall-action', { action: next, params: {} })
}

async function submitPortRule(rule) {
  const p = Number(portInput.value)
  if (!Number.isInteger(p) || p < 1 || p > 65535) return
  const portSpec = `${p}/${portProto.value}`
  const isDeny = rule === 'deny'
  const ok = await confirmAction({
    title: isDeny ? 'Block Port (Firewall)' : 'Allow Port (Firewall)',
    message: `${isDeny ? 'Block' : 'Allow'} traffic on port '${portSpec}' via host firewall?`,
    confirmText: isDeny ? 'Block Port' : 'Allow Port',
    variant: isDeny ? 'danger' : 'primary',
  })
  if (!ok) return
  emit('firewall-action', { action: 'firewall_port_rule', params: { port: portSpec, rule } })
  portInput.value = ''
}

function submitBlockIp() {
  const ip = blockIpInput.value.trim()
  if (!ip) return
  emit('firewall-action', { action: 'block_ip', params: { ip, ips: [ip], comment: blockCommentInput.value.trim() } })
  blockIpInput.value = ''
  blockCommentInput.value = ''
}

async function unblockIp(ip) {
  const ok = await confirmAction({
    title: 'Unblock IP Address',
    message: `Remove DROP rule for ${ip} from host firewall?`,
    confirmText: 'Unblock',
    variant: 'warning',
  })
  if (!ok) return
  emit('firewall-action', { action: 'unblock_ip', params: { ip, ips: [ip] } })
}

async function copyIp(ip) {
  try {
    await navigator.clipboard.writeText(ip)
    copiedIp.value = ip
    setTimeout(() => { copiedIp.value = '' }, 1800)
  } catch (e) {}
}
</script>
