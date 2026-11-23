export function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function formatUptime(secs, locale = 'en') {
  if (!secs || secs <= 0) return '-'
  const isId = (typeof locale === 'string' ? locale : locale?.value) === 'id'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) {
    if (isId) return h > 0 ? `${d}h ${h}j` : `${d} hari`
    return h > 0 ? `${d}d ${h}h` : `${d} days`
  }
  if (h > 0) {
    if (isId) return `${h}j ${m}m`
    return `${h}h ${m}m`
  }
  return isId ? `${m} mnt` : `${m}m`
}

export function formatIncidentTime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
    const day = String(d.getDate()).padStart(2, '0')
    const mon = months[d.getMonth()]
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    return `${day} ${mon} ${h}:${m}`
  } catch {
    return isoStr
  }
}

export function formatIncidentDuration(startedAt, locale = 'en') {
  if (!startedAt) return '-'
  const isId = (typeof locale === 'string' ? locale : locale?.value) === 'id'
  try {
    const start = new Date(startedAt).getTime()
    const diff = Math.max(0, Math.floor((Date.now() - start) / 1000))
    if (diff < 60) return isId ? `${diff} dtk` : `${diff}s`
    const d = Math.floor(diff / 86400)
    const h = Math.floor((diff % 86400) / 3600)
    const m = Math.floor((diff % 3600) / 60)
    if (d > 0) {
      if (isId) return h > 0 ? `${d} h ${h} j` : `${d} hari`
      return h > 0 ? `${d}d ${h}h` : `${d}d`
    }
    if (h > 0) {
      if (isId) return `${h} j ${m} mnt`
      return `${h}h ${m}m`
    }
    return isId ? `${m} mnt` : `${m}m`
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

export function formatIncidentMessage(prob, locale = 'en') {
  if (!prob) return ''
  const isEn = (typeof locale === 'string' ? locale : locale?.value) === 'en'
  const key = prob.key || ''
  const rawMsg = prob.message || ''

  if (key === 'apt_updates' || key === 'pkg_updates' || rawMsg.includes('menunggu upgrade') || rawMsg.includes('paket pembaruan')) {
    const countMatch = rawMsg.match(/(\d+)/)
    const count = countMatch ? countMatch[1] : ''
    if (isEn) {
      return `${count} packages pending upgrade`.trim()
    }
    return `${count} paket menunggu upgrade`.trim()
  }

  if (key.startsWith('service_down:')) {
    const svc = key.split(':')[1] || ''
    if (isEn) {
      return `Service ${svc} Down`
    }
    return `Layanan ${svc} Down`
  }

  if (key === 'agent_stale') {
    const durMatch = rawMsg.match(/(\d+)\s*(mnt|min|m)/i)
    const dur = durMatch ? durMatch[1] : '5'
    const isOffline = rawMsg.toLowerCase().includes('offline')
    if (isEn) {
      return `Agent not reporting (> ${dur} mins)${isOffline ? ' — ASSET OFFLINE' : ''}`
    }
    return `Agen tidak melapor (> ${dur} mnt)${isOffline ? ' — ASET OFFLINE' : ''}`
  }

  if (key.startsWith('ssh_active_session:')) {
    const target = key.replace('ssh_active_session:', '')
    if (isEn) {
      return `Active SSH Session: ${target}`
    }
    return `Sesi SSH Aktif: ${target}`
  }

  if (key.includes('cpu')) {
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    if (isEn) {
      return `High CPU utilization: ${pct}`
    }
    return `Utilisasi CPU tinggi: ${pct}`
  }

  if (key.includes('ram')) {
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    const isDanger = key === 'ram_danger' || rawMsg.toLowerCase().includes('kritis')
    if (isEn) {
      return isDanger ? `Critical RAM allocation: ${pct}` : `High RAM allocation: ${pct}`
    }
    return isDanger ? `Alokasi RAM kritis: ${pct}` : `Alokasi RAM tinggi: ${pct}`
  }

  if (key === 'disk_ro_root') {
    if (isEn) return 'Root filesystem (/) switched to Read-Only mode'
    return 'Filesystem root (/) beralih ke mode Read-Only'
  }

  if (key.startsWith('disk_danger:') || key.startsWith('disk_warning:')) {
    const mount = key.split(':')[1] || '/'
    const pctMatch = rawMsg.match(/([\d.]+)%/)
    const pct = pctMatch ? `${pctMatch[1]}%` : ''
    const isDanger = key.startsWith('disk_danger:')
    if (isEn) {
      return isDanger ? `Storage almost exhausted on ${mount}: ${pct}` : `High storage capacity on ${mount}: ${pct}`
    }
    return isDanger ? `Kapasitas penyimpanan hampir habis pada ${mount}: ${pct}` : `Kapasitas penyimpanan tinggi pada ${mount}: ${pct}`
  }

  return rawMsg
}

export function formatIncidentTip(prob, locale = 'en') {
  if (!prob) return ''
  const isEn = (typeof locale === 'string' ? locale : locale?.value) === 'en'
  const key = prob.key || ''
  const rawTip = prob.tip || ''

  if (key === 'apt_updates' || key === 'pkg_updates') {
    if (isEn) {
      return 'Open asset workspace and select Update OS or Upgrade. Manual: sudo apt update && sudo apt upgrade'
    }
    return 'Buka rincian aset lalu pilih Update OS atau Upgrade. Manual: sudo apt update && sudo apt upgrade'
  }

  if (key.startsWith('service_down:')) {
    const svc = key.split(':')[1] || 'service'
    if (isEn) {
      return `Check status: sudo systemctl status ${svc} | Restart: sudo systemctl restart ${svc} | Logs: journalctl -u ${svc} -n 50`
    }
    return `Cek status: sudo systemctl status ${svc} | Mulai ulang: sudo systemctl restart ${svc} | Log: journalctl -u ${svc} -n 50`
  }

  if (key === 'agent_stale') {
    if (isEn) {
      return 'Vital services affected. Check pantau-agent daemon or network connectivity.'
    }
    return 'Layanan vital terganggu. Periksa daemon pantau-agent atau konektivitas jaringan.'
  }

  if (key.startsWith('ssh_active_session:')) {
    if (isEn) {
      return 'Remote terminal session in progress. Verify this activity is authorized.'
    }
    return 'Sesi login terminal remote sedang berlangsung. Pastikan aktivitas ini sah.'
  }

  if (key.includes('cpu')) {
    if (isEn) return 'CPU utilization exceeds designated 85% normal threshold.'
    return 'Utilisasi CPU melampaui batas ambang normal 85%.'
  }

  if (key.includes('ram')) {
    if (isEn) return 'Physical RAM memory usage approached designated operational threshold.'
    return 'Ketersediaan memori fisik hampir habis. Waspadai pemanggilan kernel OOM Killer.'
  }

  if (key === 'disk_ro_root') {
    if (isEn) return 'System integrity risk! Kernel locked storage to read-only to prevent corruption.'
    return 'Bahaya integritas sistem! Kernel mengunci penyimpanan ke read-only untuk mencegah korupsi data.'
  }

  if (key.startsWith('disk_danger:') || key.startsWith('disk_warning:')) {
    const mount = key.split(':')[1] || '/'
    if (isEn) return `Partition ${mount} storage capacity threshold reached. Perform log cleanup or disk expansion.`
    return `Partisi ${mount} melampaui batas aman. Segera lakukan pembersihan log atau ekspansi disk.`
  }

  return rawTip
}
