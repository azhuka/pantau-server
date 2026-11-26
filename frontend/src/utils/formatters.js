export function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function formatUptime(secs) {
  if (!secs || secs <= 0) return '-'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export function formatIncidentTime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const day = String(d.getDate()).padStart(2, '0')
    const mon = months[d.getMonth()]
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    return `${day} ${mon} ${h}:${m}`
  } catch {
    return isoStr
  }
}

export function formatFullTime(isoStr) {
  if (!isoStr) return '-'
  try {
    return new Date(isoStr).toLocaleString('en-GB', { hour12: false })
  } catch {
    return String(isoStr)
  }
}

export function formatRelativeTime(isoStr) {
  if (!isoStr) return 'Never'
  try {
    const diffSec = Math.max(0, Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000))
    if (diffSec < 60) return `${diffSec}s ago`
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
    return `${Math.floor(diffSec / 86400)}d ago`
  } catch {
    return String(isoStr)
  }
}

export function severityBadgeClass(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'danger') return 'bg-rose-950/90 text-rose-300 border-rose-600/80'
  if (s === 'critical' || s === 'average') return 'bg-orange-950/90 text-orange-300 border-orange-600/80'
  if (s === 'warning') return 'bg-amber-950/90 text-amber-300 border-amber-600/80'
  return 'bg-sky-950/90 text-sky-300 border-sky-600/80'
}

export function formatIncidentDuration(startedAt, _locale = null, resolvedAt = null) {
  if (!startedAt) return '-'
  try {
    const start = new Date(startedAt).getTime()
    const end = resolvedAt ? new Date(resolvedAt).getTime() : Date.now()
    const diff = Math.max(0, Math.floor((end - start) / 1000))
    if (diff < 60) return `${diff}s`
    const d = Math.floor(diff / 86400)
    const h = Math.floor((diff % 86400) / 3600)
    const m = Math.floor((diff % 3600) / 60)
    if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`
    if (h > 0) return `${h}h ${m}m`
    return `${m}m`
  } catch {
    return '-'
  }
}

export function getMeterLitSegments(val) {
  if (val === null || val === undefined || isNaN(val) || val <= 0) return 0
  if (val < 5) return 1
  return Math.min(10, Math.round(val / 10))
}

export function getMeterClass(val) {
  if (val >= 95) return 'on-red'
  if (val >= 90) return 'on-orange'
  if (val >= 85) return 'on-yellow'
  return 'on-green'
}

export function getMeterColor(val) {
  if (val >= 95) return '#ef4444'
  if (val >= 90) return '#f97316'
  if (val >= 85) return '#f59e0b'
  return '#10b981'
}

export function isServerOnline(s) {
  if (!s) return false
  if (s.is_online !== undefined) return Boolean(s.is_online)
  if (s.last_seen) {
    const last = new Date(s.last_seen).getTime()
    return (Date.now() - last) <= 60000
  }
  return false
}

export function formatIncidentMessage(prob) {
  if (!prob) return ''
  const key = prob.key || ''
  const rawMsg = prob.message || ''

  if (key === 'apt_updates' || key === 'pkg_updates' || rawMsg.includes('menunggu upgrade') || rawMsg.includes('paket pembaruan')) {
    const countMatch = rawMsg.match(/(\d+)/)
    const count = countMatch ? countMatch[1] : ''
    return `${count} packages pending upgrade`.trim()
  }

  if (key.startsWith('service_down:')) {
    const svc = key.split(':')[1] || ''
    return `Service ${svc} Down`
  }

  if (key === 'agent_stale') {
    const durMatch = rawMsg.match(/(\d+)\s*(mnt|min|m)/i)
    const dur = durMatch ? durMatch[1] : '5'
    const isOffline = rawMsg.toLowerCase().includes('offline')
    return `Agent not reporting (> ${dur} mins)${isOffline ? ' — ASSET OFFLINE' : ''}`
  }

  if (key.startsWith('ssh_active_session:')) {
    const target = key.replace('ssh_active_session:', '')
    return `Active SSH Session: ${target}`
  }

  if (key.includes('cpu')) {
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    return `High CPU utilization: ${pct}`
  }

  if (key.includes('ram')) {
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    const isDanger = key === 'ram_danger' || rawMsg.toLowerCase().includes('kritis')
    return isDanger ? `Critical RAM allocation: ${pct}` : `High RAM allocation: ${pct}`
  }

  if (key === 'disk_ro_root') {
    return 'Root filesystem (/) switched to Read-Only mode'
  }

  if (key.startsWith('disk_danger:') || key.startsWith('disk_warning:')) {
    const mount = key.split(':')[1] || '/'
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    const isDanger = key.startsWith('disk_danger:')
    return isDanger ? `Storage almost exhausted on ${mount}: ${pct}` : `High storage capacity on ${mount}: ${pct}`
  }

  if (key.startsWith('fim_anomaly:')) {
    const path = key.slice('fim_anomaly:'.length) || '/'
    return `File Integrity Changed: ${path}`
  }

  if (key.startsWith('probe_failed:')) {
    return rawMsg
      .replace(/\bGAGAL:/g, 'Failed:')
      .replace(/Timeout membaca respons/gi, 'Response read timeout')
      .replace(/Gagal terhubung/gi, 'Connection failed')
      .replace(/Koneksi ditolak/gi, 'Connection refused')
      .replace(/Gagal resolve DNS/gi, 'DNS resolution failed')
  }

  return rawMsg
}

export function formatIncidentRootCause(prob) {
  const k = prob?.key || ''
  if (k.startsWith('ssh_active_session:')) return 'Active remote interactive SSH login session detected on host.'
  if (k.startsWith('service_down:')) return `System service unit (${k.split(':')[1] || 'service'}) is inactive or failed.`
  if (k === 'failed_logins') return 'Repeated SSH authentication failures detected from external IP(s).'
  if (k.includes('pkg_updates') || k.includes('apt_updates')) return 'Linux package repository indicates pending OS or security updates.'
  if (k === 'agent_stale') return 'Host telemetry heartbeat stopped for more than 60 seconds.'
  if (k === 'agent_outdated') return 'Remote pantau-agent version is behind the control-plane version.'
  if (k.startsWith('fim_anomaly:')) return 'File integrity baseline mismatch detected on monitored system path.'
  if (k.startsWith('oom_kill:')) return 'Linux kernel Out-Of-Memory killer terminated a process due to memory exhaustion.'
  if (k.startsWith('disk_io_error')) return 'Kernel reported physical or virtual block device I/O errors.'
  if (k.includes('kernel_panic')) return 'Critical kernel panic or fatal hardware/driver fault detected.'
  if (k.includes('cpu')) return 'CPU computing load exceeded designated operational threshold limit.'
  if (k.includes('ram') || k.includes('swap')) return 'Physical RAM or swap memory usage exceeded safe operational threshold.'
  if (k.includes('disk') || k.includes('mount_')) return 'Filesystem storage volume utilization exceeded safe operating quota.'
  return 'Telemetry anomaly detected by Pantau Server evaluation engine.'
}

export function formatIncidentTip(prob) {
  if (!prob) return ''
  const key = prob.key || ''
  const rawTip = prob.tip || ''

  if (key === 'apt_updates' || key === 'pkg_updates') {
    return 'Open Server Details and select Update OS or Upgrade OS. Manual: sudo apt update && sudo apt upgrade'
  }

  if (key.startsWith('service_down:')) {
    const svc = key.split(':')[1] || 'service'
    return `Check status: sudo systemctl status ${svc} | Restart: sudo systemctl restart ${svc} | Logs: journalctl -u ${svc} -n 50`
  }

  if (key === 'agent_stale') {
    return 'Vital services affected. Check pantau-agent daemon or network connectivity.'
  }

  if (key.startsWith('ssh_active_session:')) {
    return 'Remote SSH session in progress. Verify this activity is authorized.'
  }

  if (key.includes('cpu')) {
    return 'CPU utilization exceeds designated 85% normal threshold.'
  }

  if (key.includes('ram')) {
    return 'Physical RAM memory usage approached designated operational threshold.'
  }

  if (key === 'disk_ro_root') {
    return 'System integrity risk! Kernel locked storage to read-only to prevent corruption.'
  }

  if (key.startsWith('disk_danger:') || key.startsWith('disk_warning:')) {
    const mount = key.split(':')[1] || '/'
    return `Partition ${mount} storage capacity threshold reached. Perform log cleanup or disk expansion.`
  }

  if (key.startsWith('fim_anomaly:')) {
    const path = key.slice('fim_anomaly:'.length) || '/'
    return `File or directory ${path} recorded a file integrity change. Open the Integrity (FIM) tab to review history or update baseline if authorized.`
  }

  if (key.startsWith('probe_failed:')) {
    return 'Verify target endpoint availability, network reachability, and service health.'
  }

  return rawTip
}
