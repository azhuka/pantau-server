<template>
  <div class="space-y-3 font-mono">
    <div class="flex items-center justify-between flex-wrap gap-2">
      <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">
        {{ t('ws_incidents_title') }}
      </h3>
      <span class="text-xs text-gray-400">
        {{ activeCount }} active<template v-if="ignoredCount > 0"> · {{ ignoredCount }} ignored</template> · {{ closedCount }} closed
      </span>
    </div>

    <NocFilterPanel
      v-if="displayList.length > 0"
      :has-active-filters="Boolean(sevFilter || searchQuery.trim())"
      :summary-text="`${filteredProblems.length} of ${displayList.length} incidents`"
      compact
      @reset="sevFilter = ''; searchQuery = ''"
    >
      <template #fields>
        <div class="noc-filter-col">
          <label class="noc-filter-label" for="ws-prob-sev">{{ t('flt_severity') }}</label>
          <select id="ws-prob-sev" v-model="sevFilter" class="noc-filter-select">
            <option value="">{{ t('flt_all_severities') }}</option>
            <option value="danger">{{ t('inc_filter_danger') }}</option>
            <option value="critical">{{ t('inc_filter_critical') }}</option>
            <option value="warning">{{ t('inc_filter_warning') }}</option>
            <option value="info">{{ t('inc_filter_info') }}</option>
            <option value="ignored">{{ t('inc_filter_ignored') }}</option>
          </select>
        </div>
        <div class="noc-filter-col-search">
          <label class="noc-filter-label" for="ws-prob-search">{{ t('flt_search') }}</label>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="ws-prob-search" v-model="searchQuery" type="search" :placeholder="t('inc_search_placeholder')" />
          </div>
        </div>
      </template>
    </NocFilterPanel>

    <div v-if="displayList.length === 0" class="hud-tactical-card rounded-xl p-8 text-center">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>
      <div class="mb-2 flex justify-center">
        <svg class="w-8 h-8 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6 9 17l-5-5"/></svg>
      </div>
      <div class="text-xs font-semibold text-gray-200">{{ t('ws_incidents_empty') }}</div>
      <div class="text-xs text-gray-400 mt-1">{{ t('ws_incidents_normal') }}</div>
    </div>

    <div v-else-if="filteredProblems.length === 0" class="hud-tactical-card rounded-xl p-6 text-center text-xs text-gray-400">
      {{ t('inc_empty_filtered') }}
    </div>

    <div v-else class="bg-[#0b1220] border border-gray-800/80 rounded-xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="bg-[#080d1a] border-b border-gray-800 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th class="py-2.5 px-3 whitespace-nowrap">Triggered At</th>
              <th class="py-2.5 px-3 text-center whitespace-nowrap">Severity</th>
              <th class="py-2.5 px-3">Incident Description</th>
              <th class="py-2.5 px-3 whitespace-nowrap">Duration</th>
              <th class="py-2.5 px-3">Solution</th>
              <th class="py-2.5 px-3 text-right whitespace-nowrap">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60">
            <tr
              v-for="prob in pagedProblems"
              :key="prob.id"
              class="hover:bg-gray-800/30 transition-colors"
              :class="{ 'opacity-55 bg-[#070b14]/50': Boolean(prob.resolved_at), 'opacity-70': !prob.resolved_at && Boolean(prob.is_ignored) }"
            >
              <td
                class="py-2.5 px-3 text-gray-400 whitespace-nowrap"
                :title="`Started: ${prob.started_at || '-'}${prob.resolved_at ? ' | Closed: ' + prob.resolved_at : ''}`"
              >
                {{ formatIncidentTime(prob.started_at) }}
              </td>
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span class="px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase border" :class="severityBadgeClass(prob.severity)">
                  {{ (prob.severity === 'average' ? 'CRITICAL' : prob.severity || 'INFO').toUpperCase() }}
                </span>
              </td>
              <td class="py-2.5 px-3 max-w-md" :class="prob.resolved_at ? 'text-gray-400' : 'text-gray-200'">
                <div class="font-medium leading-snug flex items-start gap-1.5">
                  <svg v-if="prob.resolved_at" class="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-label="Closed / Resolved"><polyline points="20 6 9 17 4 12"/></svg>
                  <span v-else class="w-2 h-2 rounded-full mt-1.5 shrink-0" :class="prob.is_ignored ? 'bg-gray-500' : 'bg-rose-400 animate-pulse'" title="Active Incident"></span>
                  <span>{{ formatIncidentMessage(prob, locale) }}</span>
                </div>
                <div class="flex items-center gap-1.5 mt-1 flex-wrap pl-3.5">
                  <span v-if="!prob.resolved_at && !prob.is_ignored" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-950/60 text-rose-300 border border-rose-700/50">
                    ACTIVE
                  </span>
                  <span v-if="prob.resolved_at" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-950/50 text-emerald-300 border border-emerald-700/50" :title="prob.resolved_note || 'Resolved'">
                    CLOSED
                  </span>
                  <span v-if="prob.acknowledged_by" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30" :title="t('dash_acked_by', { user: prob.acknowledged_by })">
                    ACKNOWLEDGED
                  </span>
                  <span v-if="prob.is_ignored" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-gray-700/60 text-gray-300 border border-gray-600" :title="prob.ignored_reason || 'Ignored'">
                    IGNORED
                  </span>
                </div>
              </td>
              <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap">
                {{ formatIncidentDuration(prob.started_at, locale, prob.resolved_at) }}
              </td>
              <td class="py-2.5 px-3 text-gray-400 max-w-xs">
                <span class="block truncate cursor-help text-[11px]" :title="formatIncidentTip(prob, locale) || '—'">
                  {{ formatIncidentTip(prob, locale) || '—' }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-right whitespace-nowrap">
                <button
                  v-if="prob.resolved_at || isViewer"
                  type="button"
                  @click="openDetail(prob)"
                  class="w-[26px] h-[26px] min-w-[26px] p-0 inline-flex items-center justify-center rounded bg-gray-800/80 hover:bg-cyan-950 text-gray-300 hover:text-cyan-300 border border-gray-700/80 transition cursor-pointer"
                  title="View Diagnostics & Details"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
                <button
                  v-else
                  type="button"
                  @click.stop="toggleActDropdown(prob, $event)"
                  class="h-6 min-w-[58px] px-2 py-0.5 rounded bg-[#080d1a] hover:bg-cyan-950/60 text-cyan-300 border border-gray-700 hover:border-cyan-500 font-bold text-[11px] transition cursor-pointer inline-flex items-center justify-between gap-1 select-none"
                >
                  <span>Actions</span>
                  <svg class="w-2.5 h-2.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <NocTablePagination
        v-model:page="currentPage"
        v-model:pageSize="pageSize"
        :total="filteredProblems.length"
        unitLabel="incidents"
        :pageSizeOptions="[10, 25, 50, 'all']"
      />
    </div>

    <Teleport to="body">
      <div
        v-if="openActId && activeActProb"
        @click.stop
        :style="actDropdownStyle"
        class="rounded-md bg-[#0a0f1d] border border-gray-700 shadow-2xl py-1 z-[100005] text-xs font-mono min-w-[185px]"
      >
        <button @click="openDetail(activeActProb); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer">
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <span>Diagnose & Details</span>
        </button>

        <button v-if="activeActProb.log_unit" @click="$emit('switch-tab', 'logs'); closeActDropdown()" class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-200 flex items-center gap-2 cursor-pointer">
          <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span>{{ activeActProb.log_unit === 'AUTH' ? 'View Auth Logs' : 'View Unit Logs' }}</span>
        </button>

        <!-- Direct Context-Aware Mitigation -->
        <template v-if="!activeActProb.resolved_at">
          <button
            v-if="activeActProb.action === 'restart_service' && hasPerm('can_services')"
            @click="mitigateRestartService(activeActProb); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            <span>Restart Service</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'terminate_session' && hasPerm('can_users_sys')"
            @click="$emit('terminate-ssh-problem', activeActProb.id); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-rose-950/60 text-rose-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            <span>Terminate Session</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'block_ip' && hasPerm('can_firewall') && getAttackerIps(activeActProb).length > 0"
            @click="mitigateBlockIps(activeActProb); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-rose-950/60 text-rose-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>Block {{ getAttackerIps(activeActProb).length }} Attacker IP(s)</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'apt_update' && hasPerm('can_apt')"
            @click="$emit('switch-tab', 'packages'); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="8 17 12 21 16 17"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/></svg>
            <span>Open Packages</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'fim_view'"
            @click="$emit('switch-tab', 'fim'); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            <span>Review File Integrity</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'update_agent' && hasPerm('can_ota')"
            @click="mitigateUpdateAgent(); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            <span>Update Agent (OTA)</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'inspect_processes'"
            @click="$emit('switch-tab', 'processes'); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            <span>Inspect Processes</span>
          </button>

          <button
            v-else-if="activeActProb.action === 'inspect_storage'"
            @click="$emit('switch-tab', 'overview'); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-cyan-950/50 text-cyan-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
            <span>Inspect Storage</span>
          </button>

          <!-- Ack / Unack -->
          <button
            v-if="activeActProb.acknowledged_by"
            @click="unackProblem(activeActProb.id); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-emerald-400 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
            :title="t('dash_acked_by', { user: activeActProb.acknowledged_by })"
          >
            <svg class="w-3.5 h-3.5 shrink-0 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>Cancel Acknowledge</span>
          </button>
          <button
            v-else
            @click="$emit('ack-problem', activeActProb.id); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>Acknowledge</span>
          </button>

          <!-- Ignore / Unignore -->
          <button
            v-if="activeActProb.is_ignored"
            @click="unignoreProblem(activeActProb.id); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-gray-800 text-gray-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            <span>Cancel Ignore</span>
          </button>
          <button
            v-else
            @click="openIgnore(activeActProb); closeActDropdown()"
            class="w-full text-left px-3 py-1.5 hover:bg-amber-950/50 text-amber-300 flex items-center gap-2 cursor-pointer border-t border-gray-800/60"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
            <span>Ignore Incident</span>
          </button>
        </template>
      </div>
    </Teleport>

    <ProblemDetailModal
      :is-open="detailModalOpen"
      :problem="selectedProb"
      :current-user="currentUser"
      @close="detailModalOpen = false"
      @ack-problem="$emit('ack-problem', $event); detailModalOpen = false"
      @ignore-problem="openIgnore($event); detailModalOpen = false"
      @open-server="detailModalOpen = false"
    />

    <IgnoreIncidentModal
      :is-open="ignoreModalOpen"
      :problem="selectedProb"
      @close="ignoreModalOpen = false"
      @ignored="onIgnored"
    />

    <!-- Table 2: Action History -->
    <WorkspaceActionHistoryTable
      :server-id="serverId"
      :refresh-key="actionRefreshKey"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'
import { formatIncidentMessage, formatIncidentTip, formatIncidentTime, formatIncidentDuration, severityBadgeClass } from '../../../utils/formatters'
import { useFloatingDropdown } from '../../../utils/useFloatingDropdown'
import { useToast, confirmAction } from '../../../utils/useToast'
import NocFilterPanel from '../../common/NocFilterPanel.vue'
import NocTablePagination from '../../common/NocTablePagination.vue'
import ProblemDetailModal from '../../dashboard/ProblemDetailModal.vue'
import IgnoreIncidentModal from '../../incidents/modals/IgnoreIncidentModal.vue'
import WorkspaceActionHistoryTable from './WorkspaceActionHistoryTable.vue'

const { t, locale } = useI18n()
const toast = useToast()

const props = defineProps({
  serverId: { type: Number, required: true },
  problems: { type: Array, default: () => [] },
  currentUser: { type: Object, default: null },
})

const emit = defineEmits(['terminate-ssh-problem', 'ack-problem', 'switch-tab', 'refresh'])

const sevFilter = ref('')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = ref(10)

const detailModalOpen = ref(false)
const ignoreModalOpen = ref(false)
const selectedProb = ref(null)
const actionRefreshKey = ref(0)

const isViewer = computed(() => !props.currentUser || ['viewer', 'guest', 'tamu'].includes((props.currentUser?.role || '').toLowerCase()))

function hasPerm(permKey) {
  if (!props.currentUser) return false
  if (props.currentUser.is_master_admin) return true
  return Boolean(props.currentUser.permissions?.[permKey])
}

const displayList = computed(() => props.problems || [])
const activeCount = computed(() => displayList.value.filter(p => !p.resolved_at && !p.is_ignored).length)
const ignoredCount = computed(() => displayList.value.filter(p => !p.resolved_at && Boolean(p.is_ignored)).length)
const closedCount = computed(() => displayList.value.filter(p => Boolean(p.resolved_at)).length)

const filteredProblems = computed(() => {
  return displayList.value.filter((p) => {
    if (sevFilter.value === 'ignored') {
      if (!p.is_ignored) return false
    } else if (sevFilter.value) {
      if (p.is_ignored) return false
      const s = (p.severity || 'info').toLowerCase()
      if (sevFilter.value === 'critical') {
        if (s !== 'critical' && s !== 'average') return false
      } else if (s !== sevFilter.value) {
        return false
      }
    }
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.toLowerCase()
      const hay = `${p.message || ''} ${p.key || ''} ${p.tip || ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

const pagedProblems = computed(() => {
  if (pageSize.value === 'all') return filteredProblems.value
  const start = (currentPage.value - 1) * pageSize.value
  return filteredProblems.value.slice(start, start + pageSize.value)
})

watch([sevFilter, searchQuery], () => { currentPage.value = 1 })

const { openId: openActId, activeItem: activeActProb, dropdownStyle: actDropdownStyle, toggle: toggleActDropdown, close: closeActDropdown } = useFloatingDropdown()

function openDetail(prob) {
  selectedProb.value = prob
  detailModalOpen.value = true
}

function openIgnore(prob) {
  selectedProb.value = prob
  ignoreModalOpen.value = true
}

function onIgnored() {
  ignoreModalOpen.value = false
  actionRefreshKey.value++
  emit('refresh')
}

function getAttackerIps(prob) {
  const src = prob?.context?.source_ips
  if (!src || typeof src !== 'object') return []
  return Object.keys(src).filter(Boolean).slice(0, 10)
}

async function dispatchAction(action, params, successMsg) {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/servers/${props.serverId}/actions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ action, params }),
    })
    const data = await res.json()
    if (!res.ok || !data.ok) {
      toast.error(data.detail || `Action '${action}' failed`)
      return false
    }
    toast.success(successMsg || data.message || 'Command queued')
    actionRefreshKey.value++
    emit('refresh')
    return true
  } catch (e) {
    toast.error(`Network error while executing '${action}'`)
    return false
  }
}

async function mitigateRestartService(prob) {
  const svcName = prob.log_unit || prob.key.split(':')[1] || ''
  if (!svcName) return
  const ok = await confirmAction({ title: 'Restart Service', message: `Restart service '${svcName}' on this host?`, variant: 'warning' })
  if (!ok) return
  await dispatchAction('restart_service', { name: svcName }, `Restart queued for ${svcName}`)
}

async function mitigateBlockIps(prob) {
  const ips = getAttackerIps(prob)
  if (!ips.length) return
  const ok = await confirmAction({ title: 'Block Attacker IPs', message: `Block ${ips.length} attacker IP(s) via host firewall: ${ips.join(', ')}?`, variant: 'danger' })
  if (!ok) return
  let blocked = 0
  for (const ip of ips) {
    const res = await dispatchAction('block_ip', { ip }, null)
    if (res) blocked++
  }
  if (blocked > 0) toast.success(`Queued firewall block for ${blocked} IP(s)`)
}

async function mitigateUpdateAgent() {
  const ok = await confirmAction({ title: 'Update Agent (OTA)', message: 'Dispatch OTA agent update to this host?', variant: 'warning' })
  if (!ok) return
  await dispatchAction('update_agent', {}, 'Agent OTA update queued')
}

async function unackProblem(pid) {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/problems/${pid}/unack`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    const data = await res.json()
    if (data.ok) {
      toast.success('Acknowledgement cleared')
      emit('refresh')
    } else {
      toast.error(data.detail || 'Failed to clear acknowledgement')
    }
  } catch (e) {
    toast.error('Network error')
  }
}

async function unignoreProblem(pid) {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/problems/${pid}/unignore`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
    const data = await res.json()
    if (data.ok) {
      toast.success('Incident monitoring resumed')
      emit('refresh')
    } else {
      toast.error(data.detail || 'Failed to resume monitoring')
    }
  } catch (e) {
    toast.error('Network error')
  }
}
</script>
