<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in font-mono">
    <div class="w-full max-w-lg bg-[#080d1a] border border-cyan-500/40 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
      <!-- Header -->
      <div class="p-4 bg-[#0a1122] border-b border-cyan-900/40 flex items-center justify-between">
        <div class="flex items-center gap-2.5">
          <div class="w-3 h-3 rounded-full bg-cyan-400"></div>
          <div>
            <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider flex items-center gap-2">
              <span>{{ user.username }}</span>
              <span
                class="text-[10px] font-bold px-2 py-0.5 rounded uppercase"
                :class="roleBadgeClass"
              >
                {{ roleLabel }}
              </span>
            </h3>
            <p class="text-[11px] text-gray-400 font-mono mt-0.5">
              ID Akun: #{{ user.id }}
            </p>
          </div>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-white text-lg p-1 transition cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Content / Body -->
      <div class="p-4 space-y-4 overflow-y-auto text-xs">
        <!-- Metadata Grid -->
        <div class="grid grid-cols-2 gap-2.5 p-3 rounded-lg bg-[#0e1628] border border-gray-800">
          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">Status Akun</span>
            <span
              class="font-bold flex items-center gap-1.5 mt-0.5"
              :class="user.is_active ? 'text-emerald-400' : 'text-rose-400'"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="user.is_active ? 'bg-emerald-400' : 'bg-rose-400'"></span>
              <span>{{ user.is_active ? 'Aktif' : 'Terkunci' }}</span>
            </span>
          </div>

          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">2FA / TOTP</span>
            <span
              class="font-bold flex items-center gap-1 mt-0.5"
              :class="user.totp_enabled ? 'text-emerald-400' : 'text-amber-400'"
            >
              <span>{{ user.totp_enabled ? '● 2FA Aktif' : '○ 2FA Nonaktif' }}</span>
            </span>
          </div>

          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">Login Terakhir</span>
            <span class="text-gray-200 mt-0.5 block">
              {{ formatTime(user.last_login_at) }}
              <span v-if="user.last_login_ip" class="text-gray-400 text-[10px]">({{ user.last_login_ip }})</span>
            </span>
          </div>

          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">Password Diubah</span>
            <span class="text-gray-200 mt-0.5 block">{{ formatTime(user.password_changed_at) }}</span>
          </div>

          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">Dibuat Pada</span>
            <span class="text-gray-200 mt-0.5 block">{{ formatTime(user.created_at) }}</span>
          </div>

          <div>
            <span class="text-[10px] text-gray-400 block uppercase font-semibold">Dibuat Oleh</span>
            <span class="text-cyan-300 font-semibold mt-0.5 block">{{ user.created_by || 'Sistem (Setup Awal)' }}</span>
          </div>
        </div>

        <!-- Scope Server Section -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-1.5">
          <div class="text-[10px] text-gray-400 uppercase font-semibold flex items-center justify-between">
            <span>Cakupan Server (Server Scope)</span>
            <span class="text-emerald-400 font-bold" v-if="!user.allowed_server_ids || user.allowed_server_ids.length === 0">
              Akses Penuh Seluruh Server
            </span>
            <span class="text-amber-400 font-bold" v-else>
              Dibatasi {{ user.allowed_server_ids.length }} Server
            </span>
          </div>
          <div v-if="user.allowed_server_ids && user.allowed_server_ids.length > 0" class="flex flex-wrap gap-1 mt-1">
            <span
              v-for="sid in user.allowed_server_ids"
              :key="sid"
              class="px-2 py-0.5 rounded text-[10px] bg-amber-950/80 border border-amber-800/60 text-amber-300 font-mono"
            >
              {{ getServerName(sid) }}
            </span>
          </div>
        </div>

        <!-- Permissions Section -->
        <div class="p-3 rounded-lg bg-[#0e1628] border border-gray-800 space-y-2">
          <div class="text-[10px] text-gray-400 uppercase font-semibold flex items-center justify-between">
            <span>Operator Permissions Matrix (16 Perms)</span>
            <span class="text-cyan-300 font-bold" v-if="user.role === 'master_admin'">16 / 16 (Full Access)</span>
            <span class="text-cyan-300 font-bold" v-else-if="user.role === 'operator'">{{ activePermCount }} / 16 Aktif</span>
            <span class="text-gray-400 font-bold" v-else>0 / 16 (Hanya-Baca)</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto pr-1">
            <div
              v-for="(meta, permKey) in permissionsMeta"
              :key="permKey"
              class="p-1.5 rounded flex items-center gap-2 border text-[11px]"
              :class="isPermActive(permKey) ? 'bg-cyan-950/40 border-cyan-800/60 text-cyan-200' : 'bg-gray-900/30 border-gray-800/40 text-gray-500'"
            >
              <span class="font-bold">{{ isPermActive(permKey) ? '✔' : '○' }}</span>
              <span class="truncate" :title="meta.desc">{{ meta.label }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="p-3 bg-[#0a1122] border-t border-cyan-900/40 flex items-center justify-between">
        <button
          @click="$emit('close')"
          class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-mono transition cursor-pointer"
        >
          Close
        </button>

        <div class="flex items-center gap-2">
          <button
            v-if="canEdit"
            @click="$emit('edit', user); $emit('close')"
            class="px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-mono font-bold transition cursor-pointer flex items-center gap-1.5"
          >
            <span>Edit Pengguna</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  user: {
    type: Object,
    required: true,
  },
  currentUserId: {
    type: Number,
    default: null,
  },
  permissionsMeta: {
    type: Object,
    default: () => ({}),
  },
  serversList: {
    type: Array,
    default: () => [],
  },
})

defineEmits(['close', 'edit'])

const roleLabel = computed(() => {
  if (props.user.role === 'master_admin') return 'Master Admin'
  if (props.user.role === 'operator') return 'Operator'
  return 'Viewer'
})

const roleBadgeClass = computed(() => {
  if (props.user.role === 'master_admin') return 'bg-cyan-950 text-cyan-300 border border-cyan-800'
  if (props.user.role === 'operator') return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  return 'bg-amber-950 text-amber-300 border border-amber-800'
})

const canEdit = computed(() => {
  if (props.user.role === 'master_admin' && props.user.id !== props.currentUserId) return false
  return true
})

function isPermActive(permKey) {
  if (props.user.role === 'master_admin') return true
  if (props.user.role === 'viewer') return false
  return Boolean(props.user.permissions && props.user.permissions[permKey])
}

const activePermCount = computed(() => {
  if (props.user.role === 'master_admin') return 16
  if (props.user.role === 'viewer') return 0
  if (!props.user.permissions) return 0
  return Object.values(props.user.permissions).filter(Boolean).length
})

function getServerName(sid) {
  const found = props.serversList.find(s => s.id === sid)
  return found ? found.hostname : `#${sid}`
}

function formatTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}
</script>
