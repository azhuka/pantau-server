<template>
  <div class="overflow-x-auto">
    <table class="w-full text-left text-xs font-mono border-collapse">
      <thead>
        <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider select-none">
          <th class="py-2.5 px-3 w-36">{{ t('audit_col_time') }}</th>
          <th class="py-2.5 px-3 w-32">{{ t('audit_col_operator') }}</th>
          <th class="py-2.5 px-3 w-40">{{ t('audit_col_target') }}</th>
          <th class="py-2.5 px-3 w-44">{{ t('audit_col_action') }}</th>
          <th class="py-2.5 px-3">{{ t('audit_col_param') }}</th>
          <th class="py-2.5 px-3 w-28 text-center">{{ t('audit_col_status') }}</th>
          <th class="py-2.5 px-3 max-w-xs">{{ t('audit_col_result') }}</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
        <tr v-for="log in rows" :key="log.id" class="hover:bg-cyan-950/20 transition">
          <td class="py-2.5 px-3 text-gray-400 whitespace-nowrap" :title="log.created_at">{{ formatCompactTime(log.created_at) }}</td>
          <td class="py-2.5 px-3 whitespace-nowrap">
            <span class="font-bold text-gray-100">{{ splitActor(log.username).main }}</span>
            <span v-if="splitActor(log.username).sub" class="block text-[11px] text-gray-400 font-normal">{{ splitActor(log.username).sub }}</span>
          </td>
          <td class="py-2.5 px-3 text-cyan-400 whitespace-nowrap font-semibold">{{ log.server_name }}</td>
          <td class="py-2.5 px-3 whitespace-nowrap">
            <span class="px-2 py-0.5 rounded text-xs font-bold border" :class="getActionBadgeClass(log.action)">
              {{ log.action_label || log.action }}
            </span>
          </td>
          <td class="py-2.5 px-3 text-gray-300 truncate max-w-[220px]" :title="log.target">{{ log.target }}</td>
          <td class="py-2.5 px-3 text-center whitespace-nowrap">
            <span class="px-2 py-0.5 rounded text-xs font-bold border" :class="statusBadgeClass(log.result)">
              {{ log.result || 'SUCCESS' }}
            </span>
          </td>
          <td class="py-2.5 px-3 text-gray-400 truncate max-w-[260px]" :title="formatResultText(log)">
            {{ formatResultText(log) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { useI18n } from '../../i18n'

const { t } = useI18n()

defineProps({
  rows: { type: Array, default: () => [] },
})

function splitActor(name) {
  const raw = String(name || '-')
  const idx = raw.indexOf(' (')
  if (idx > 0) return { main: raw.slice(0, idx), sub: raw.slice(idx + 1) }
  return { main: raw, sub: '' }
}

function formatCompactTime(ts) {
  if (!ts || ts === '-') return '-'
  return ts.length >= 16 ? ts.slice(0, 16) : ts
}

function formatResultText(log) {
  const detail = (log.result_detail || '').trim()
  if (detail && detail !== 'SUCCESS') return detail
  if (log.meta) {
    try {
      const parsed = typeof log.meta === 'string' ? JSON.parse(log.meta) : log.meta
      if (parsed && typeof parsed === 'object') {
        return Object.entries(parsed).map(([k, v]) => `${k}=${v}`).join(', ')
      }
    } catch { return String(log.meta) }
  }
  return detail || log.result || '-'
}

function statusBadgeClass(res) {
  const up = String(res || '').toUpperCase()
  if (up === 'FAILED') return 'bg-rose-950 text-rose-300 border-rose-800'
  if (up === 'EXECUTING') return 'bg-cyan-950 text-cyan-300 border-cyan-700'
  if (up === 'PENDING') return 'bg-amber-950 text-amber-300 border-amber-800'
  return 'bg-emerald-950 text-emerald-300 border-emerald-800'
}

function getActionBadgeClass(action) {
  const act = String(action).toLowerCase()
  if (act.includes('delete') || act.includes('rm') || act.includes('kill') || act.includes('block') || act.includes('lock') || act.includes('poweroff') || act.includes('terminate')) {
    return 'bg-rose-950/80 text-rose-300 border-rose-800'
  }
  if (act.includes('add') || act.includes('create') || act.includes('start') || act.includes('unlock') || act.includes('enable')) {
    return 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
  }
  if (act.includes('update') || act.includes('upgrade') || act.includes('restart') || act.includes('reset') || act.includes('maintenance')) {
    return 'bg-amber-950/80 text-amber-300 border-amber-800'
  }
  return 'bg-cyan-950 text-cyan-300 border-cyan-800'
}
</script>