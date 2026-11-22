export function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export function formatUptime(secs) {
  if (!secs) return '-'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  return `${h}h ${m}m`
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
