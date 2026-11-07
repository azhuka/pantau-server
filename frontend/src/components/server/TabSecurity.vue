<template>
  <div class="space-y-4">
    <!-- Active TTY Sessions -->
    <div class="noc-card p-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>👤</span>
        <span>Sesi Login Terminal Aktif (who / w)</span>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Pengguna</th>
              <th>TTY / PTS</th>
              <th>Alamat IP Sumber</th>
              <th>Waktu Masuk</th>
              <th class="w-24 text-right">Tindakan</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in activeSessions" :key="`${s.user}-${s.tty}`">
              <td class="font-bold text-xs text-noc-cyan">{{ s.user }}</td>
              <td class="font-mono text-xs text-noc-text">{{ s.tty }}</td>
              <td class="font-mono text-xs text-noc-dim">{{ s.from || 'Lokal' }}</td>
              <td class="font-mono text-xs text-noc-muted">{{ s.time || '—' }}</td>
              <td class="text-right">
                <button
                  @click="terminateSession(s)"
                  class="noc-btn noc-btn-secondary py-0.5 px-2 text-[10px] text-rose-400"
                  title="Putuskan koneksi sesi"
                >
                  Putuskan
                </button>
              </td>
            </tr>
            <tr v-if="activeSessions.length === 0">
              <td colspan="5" class="text-center py-4 text-noc-muted">Tidak ada sesi login SSH/TTY aktif saat ini</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Linux User Accounts Table -->
    <div class="noc-card p-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>📋</span>
        <span>Daftar Akun Pengguna Sistem Linux (/etc/passwd)</span>
      </h3>
      <div class="overflow-x-auto max-h-80">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Username</th>
              <th>UID:GID</th>
              <th>Grup</th>
              <th>Direktori Beranda</th>
              <th>Shell Default</th>
              <th>Hak Istimewa</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in accounts" :key="u.user">
              <td class="font-bold text-xs text-noc-text">{{ u.user }}</td>
              <td class="font-mono text-[11px] text-noc-muted">{{ u.uid }}:{{ u.gid }}</td>
              <td class="text-xs text-noc-dim truncate max-w-[140px]">{{ (u.groups || []).join(', ') || u.group }}</td>
              <td class="font-mono text-[11px] text-noc-muted">{{ u.home }}</td>
              <td class="font-mono text-[11px] text-noc-dim">{{ u.shell }}</td>
              <td>
                <span v-if="u.is_sudo" class="noc-badge noc-badge-amber text-[9px]">SUDO</span>
                <span v-else class="text-noc-muted text-[10px]">Standar</span>
              </td>
              <td>
                <span
                  class="noc-badge text-[9px]"
                  :class="u.is_locked ? 'noc-badge-red' : 'noc-badge-green'"
                >
                  {{ u.is_locked ? 'TERKUNCI' : 'AKTIF' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
  overview: Object,
})

const accounts = computed(() => {
  return props.overview?.accounts || []
})

const activeSessions = computed(() => {
  const list = []
  for (const acc of accounts.value) {
    if (Array.isArray(acc.sessions)) {
      for (const s of acc.sessions) {
        list.push({ ...s, user: acc.user })
      }
    }
  }
  return list
})

async function terminateSession(session) {
  if (!confirm(`Putuskan paksa sesi TTY ${session.tty} milik pengguna ${session.user}?`)) return
  try {
    await api.post(`/servers/${props.serverId}/sessions/terminate`, {
      user: session.user,
      tty: session.tty,
    })
    alert('Perintah pemutusan sesi telah dikirim ke agen.')
  } catch (err) {
    alert('Gagal memutuskan sesi: ' + err.message)
  }
}
</script>
