/**
 * Shared pure filter helpers matching blueprint NOC rules across views and tabs.
 */

export function isUngroupedValue(val) {
  const s = String(val || '').trim()
  return !s || s.toLowerCase() === 'default'
}

export function extractGroupOptions(servers) {
  const counts = {}
  let ungroupedCount = 0
  for (const s of servers || []) {
    const g = String(s.group_name || '').trim()
    if (isUngroupedValue(g)) {
      ungroupedCount++
    } else {
      counts[g] = (counts[g] || 0) + 1
    }
  }
  const groups = Object.keys(counts).sort((a, b) => a.localeCompare(b))
  return { groups, counts, ungroupedCount }
}

export function matchesGroupFilter(itemGroup, selectedGroup) {
  if (!selectedGroup) return true
  if (selectedGroup === '__none__') return isUngroupedValue(itemGroup)
  return String(itemGroup || '').trim() === selectedGroup
}

export function matchesAssetStatus(server, statusFilter) {
  if (!statusFilter || statusFilter === 'all') return true
  if (statusFilter === 'online') return Boolean(server.is_online && !server.is_maintenance)
  if (statusFilter === 'offline' || statusFilter === 'down') return Boolean(!server.is_online && !server.is_maintenance)
  if (statusFilter === 'problem') return Number(server.active_problems_count || 0) > 0
  if (statusFilter === 'maint') return Boolean(server.is_maintenance)
  return true
}

export function buildAssetSearchHaystack(s) {
  const parts = [
    s.hostname,
    s.ip_address,
    s.net_iface,
    s.group_name,
    s.tags,
    s.os_label,
    s.kernel,
    s.hardware_model,
    s.platform_label,
    s.platform_short,
    s.notes,
    s.agent_version,
    s.is_maintenance ? 'maintenance' : '',
    s.is_proxmox_ha ? 'proxmox ha' : '',
    Number(s.apt_upgradable || 0) > 0 ? 'apt upgradable update' : '',
  ]
  return parts.filter(Boolean).join(' ').toLowerCase()
}

export const RESOLUTION_TYPE_LABELS = {
  auto: 'Auto-Healed',
  manual: 'Remediated by Operator',
  online: 'Host Reconnected (Online)',
  service_up: 'Service Restored',
  stale_closed: 'Closed (Host Offline)',
  session_closed: 'SSH Session Terminated',
  dedup: 'Deduplicated',
}

export function inferResolutionType(prob) {
  if (prob.res_type) return prob.res_type
  if (prob.acknowledged_by) return 'manual'
  const note = String(prob.resolved_note || '').toLowerCase()
  if (note === 'manual' || note.includes('operator')) return 'manual'
  if (note.includes('server_online')) return 'online'
  if (note.includes('service_up')) return 'service_up'
  if (note.includes('server_offline') || note.includes('stale')) return 'stale_closed'
  if (note.includes('session_closed') || note.includes('ssh')) return 'session_closed'
  if (note.includes('duplicate') || note.includes('dedup')) return 'dedup'
  return 'auto'
}
