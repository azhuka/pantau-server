<template>
  <div class="space-y-4">
    <div class="noc-card p-3">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim flex items-center gap-2">
          <span>🔒</span>
          <span>Sertifikat SSL / TLS & Pemantauan Kedaluwarsa</span>
        </h3>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Domain / Subjek</th>
              <th>Penerbit (Issuer)</th>
              <th>Kedaluwarsa Pada</th>
              <th>Sisa Hari</th>
              <th class="w-24 text-center">Status</th>
              <th>Lokasi Berkas</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in certs" :key="c.path">
              <td class="font-bold text-xs text-noc-cyan">
                <div>{{ c.subject || (c.domains || [])[0] || 'SSL Cert' }}</div>
                <div v-if="(c.domains || []).length > 1" class="text-[10px] text-noc-dim mt-0.5 truncate max-w-xs font-mono">
                  SAN: {{ c.domains.join(', ') }}
                </div>
              </td>
              <td class="text-xs text-noc-text truncate max-w-[140px]">{{ c.issuer || '—' }}</td>
              <td class="font-mono text-xs text-noc-muted">{{ c.not_after || '—' }}</td>
              <td class="font-mono text-xs font-bold">
                <span :class="c.days_left < 7 ? 'text-rose-400' : c.days_left < 30 ? 'text-amber-400' : 'text-emerald-400'">
                  {{ c.days_left !== undefined ? `${c.days_left} hari` : '—' }}
                </span>
              </td>
              <td class="text-center">
                <span
                  class="noc-badge uppercase font-bold"
                  :class="c.is_expired ? 'noc-badge-red' : c.is_critical ? 'noc-badge-red' : c.is_warning ? 'noc-badge-amber' : 'noc-badge-green'"
                >
                  {{ c.is_expired ? 'KEDALUWARSA' : c.is_critical ? 'KRITIS' : c.is_warning ? 'PERINGATAN' : 'VALID' }}
                </span>
              </td>
              <td class="font-mono text-[11px] text-noc-muted truncate max-w-[180px]">{{ c.path }}</td>
            </tr>
            <tr v-if="certs.length === 0">
              <td colspan="6" class="text-center py-6 text-noc-muted">Tidak ada sertifikat SSL/TLS yang terdeteksi di jalur standar</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: Object,
})

const certs = computed(() => {
  return props.overview?.ssl_certs || []
})
</script>
