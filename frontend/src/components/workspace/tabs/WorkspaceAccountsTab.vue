<template>
  <div class="space-y-4 font-mono">
    <!-- Card 1: Active Remote SSH Sessions -->
    <div class="hud-tactical-card rounded-xl p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">{{ t('ws_ssh_active_title') }}</h3>
        <span v-if="(activeSSHSessions || []).length > 0" class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 radar-warning">
          {{ activeSSHSessions.length }} {{ t('ws_ssh_sessions_count') }}
        </span>
      </div>
      <div v-if="(activeSSHSessions || []).length === 0" class="text-xs text-gray-400 py-5 text-center">
        {{ t('ws_ssh_empty') }}
      </div>
      <div v-else class="space-y-2">
        <div v-for="(s, idx) in activeSSHSessions" :key="idx" class="p-3 bg-amber-950/20 border border-amber-700/60 rounded-lg flex items-center justify-between gap-2 flex-wrap">
          <div class="flex items-center gap-3">
            <svg class="w-5 h-5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21 2-2 2m-1.5 1.5L14 9l-2-2-4 4 2 2-3 3-2-2-3 3v4h4l3-3-2-2 3-3 2 2 4-4-2-2 3.5-3.5Z"/></svg>
            <div>
              <div class="text-xs font-bold text-amber-300">{{ s.user }} <span class="text-gray-400 font-normal">{{ t('ws_connected_from') }}</span> {{ s.from }}</div>
              <div class="text-xs text-gray-400 mt-0.5">TTY: {{ s.tty }} · {{ t('dash_col_time') }}: {{ s.time || '-' }}</div>
            </div>
          </div>
          <button
            v-if="!isViewer"
            type="button"
            :disabled="!isOnline"
            @click="$emit('terminate-ssh', s.user, s.tty)"
            class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white font-bold text-xs transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? `Terminate active SSH session for ${s.user} on ${s.tty}` : 'Server offline — action disabled'"
          >
            {{ t('ws_sever_ssh_btn') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Card 2: Local User Accounts & System Groups -->
    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-cyan-500/20">
        <div class="flex items-center gap-2">
          <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">{{ subView === 'users' ? t('ws_accounts_title') : 'System Groups (/etc/group)' }}</h3>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-[11px]">
            <button type="button" @click="subView = 'users'" class="px-2.5 py-1 rounded transition cursor-pointer" :class="subView === 'users' ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'">
              Users ({{ (accountsList || []).length }})
            </button>
            <button type="button" @click="subView = 'groups'" class="px-2.5 py-1 rounded transition cursor-pointer" :class="subView === 'groups' ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'">
              Groups ({{ (groupsList || []).length }})
            </button>
          </div>
          <button
            v-if="subView === 'users' && !isViewer"
            type="button"
            :disabled="!isOnline"
            @click="showCreateForm = !showCreateForm"
            class="px-2.5 py-1 rounded text-[11px] font-bold bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-600/50 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            :title="isOnline ? 'Create a new Linux user account' : 'Server offline — action disabled'"
          >
            + Add User
          </button>
        </div>
      </div>

      <!-- Create User Form -->
      <form v-if="showCreateForm && subView === 'users' && !isViewer" @submit.prevent="submitCreateUser" class="grid grid-cols-1 sm:grid-cols-5 gap-2 p-3 rounded-lg bg-[#060a14] border border-cyan-800/50 text-xs">
        <input v-model="createForm.username" type="text" required placeholder="Username (lowercase)" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
        <input v-model="createForm.password" type="password" required placeholder="Password" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none focus:border-cyan-500" />
        <select v-model="createForm.shell" class="px-2.5 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-100 outline-none">
          <option value="/bin/bash">/bin/bash</option>
          <option value="/bin/sh">/bin/sh</option>
          <option value="/usr/sbin/nologin">/usr/sbin/nologin</option>
        </select>
        <label class="flex items-center gap-2 px-2 text-gray-300 cursor-pointer">
          <input v-model="createForm.is_sudo" type="checkbox" class="accent-cyan-500" />
          <span>Sudo Access</span>
        </label>
        <div class="flex items-center gap-1.5">
          <button type="submit" :disabled="!isOnline" class="flex-1 px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer disabled:opacity-50">Create</button>
          <button type="button" @click="showCreateForm = false" class="px-2.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
        </div>
      </form>

      <template v-if="subView === 'users'">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-[11px]">
            <button v-for="f in userFilters" :key="f.id" type="button" @click="userCategory = f.id" class="px-2.5 py-1 rounded transition cursor-pointer" :class="userCategory === f.id ? 'bg-cyan-950 text-cyan-300 font-bold' : 'text-gray-400 hover:text-white'">
              {{ f.label }}
            </button>
          </div>
          <div class="noc-filter-search-box">
            <svg class="w-3.5 h-3.5 text-gray-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input id="acc-search-input" v-model="search" type="search" placeholder="Search username, UID, shell, home..." />
          </div>
        </div>

        <div class="overflow-x-auto max-h-[380px]">
          <table class="w-full text-left text-xs border-collapse">
            <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
              <tr>
                <th class="py-2 px-3">{{ t('ws_col_username') }}</th>
                <th class="py-2 px-3">{{ t('ws_col_uid') || 'UID' }}</th>
                <th class="py-2 px-3">{{ t('ws_col_groups') }}</th>
                <th class="py-2 px-3">{{ t('ws_col_home') }} &amp; {{ t('ws_col_shell') }}</th>
                <th class="py-2 px-3">{{ t('ws_col_sessions_login') }}</th>
                <th class="py-2 px-3 text-center">{{ t('col_actions') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-800/40">
              <tr v-if="paginatedAccounts.length === 0">
                <td colspan="6" class="py-8 text-center text-gray-500 italic">No user accounts match the selected filter.</td>
              </tr>
              <tr v-for="(acc, idx) in paginatedAccounts" :key="`${acc.user || acc.name}-${idx}`" class="hover:bg-cyan-950/20">
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="font-semibold text-gray-100">{{ acc.user || acc.name }}</span>
                  <span v-if="acc.is_sudo" class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-800">Sudoer</span>
                  <span class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold" :class="acc.is_system ? 'bg-gray-800 text-gray-400' : 'bg-emerald-950 text-emerald-300'">{{ acc.is_system ? 'System' : 'Regular' }}</span>
                  <span v-if="acc.is_locked" class="ml-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-950 text-amber-300 border border-amber-800">Locked</span>
                </td>
                <td class="py-2 px-3 text-gray-400 whitespace-nowrap">{{ acc.uid ?? '-' }} / {{ acc.gid ?? '-' }}</td>
                <td class="py-2 px-3">
                  <span class="text-gray-200 font-semibold">{{ acc.group || '-' }}</span>
                  <div v-if="(acc.groups || []).length" class="flex gap-1 flex-wrap mt-0.5">
                    <span v-for="g in acc.groups.slice(0, 3)" :key="g" class="px-1 rounded bg-gray-900 border border-gray-800 text-[9px] text-gray-400">{{ g }}</span>
                    <span v-if="acc.groups.length > 3" class="text-[9px] text-cyan-400" :title="acc.groups.join(', ')">+{{ acc.groups.length - 3 }}</span>
                  </div>
                </td>
                <td class="py-2 px-3">
                  <div class="text-gray-400 text-[11px] truncate max-w-[170px]" :title="acc.home || '-'">{{ acc.home || '-' }}</div>
                  <div class="text-[11px]" :class="isInteractiveShell(acc.shell) ? 'text-cyan-400' : 'text-gray-500'">{{ acc.shell || '-' }}</div>
                </td>
                <td class="py-2 px-3 text-[11px]">
                  <div v-if="(acc.sessions || []).length" class="flex flex-wrap gap-1 mb-0.5">
                    <span v-for="s in acc.sessions" :key="s.tty" class="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[9px]">{{ s.tty }}{{ s.from ? ` @ ${s.from}` : '' }}</span>
                  </div>
                  <div v-else-if="acc.procs_count > 0" class="text-cyan-300 text-[10px]">{{ acc.procs_count }} active procs</div>
                  <div class="text-gray-500">{{ acc.last_login || '-' }}</div>
                </td>
                <td class="py-2 px-3 text-center">
                  <button
                    v-if="isViewer"
                    type="button"
                    @click="openUserActivity(acc.user || acc.name)"
                    class="w-[26px] h-[26px] min-w-[26px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 text-cyan-300 inline-flex items-center justify-center cursor-pointer"
                    :title="`View activity for ${acc.user || acc.name}`"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                  </button>
                  <button
                    v-else
                    type="button"
                    @click.stop="openMenu(acc, $event)"
                    class="px-2 h-[24px] min-w-[58px] rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-[11px] font-bold transition cursor-pointer inline-flex items-center justify-center gap-1"
                    :title="`Actions for ${acc.user || acc.name}`"
                  >
                    <span>Actions</span>
                    <span class="text-[9px]">▾</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <NocTablePagination v-model:page="currentPage" v-model:pageSize="pageSize" :total="filteredAccounts.length" unitLabel="accounts" :pageSizeOptions="[10, 25, 50, 'all']" />
      </template>

      <WorkspaceGroupsTable v-else :groups="groupsList" />
    </div>

    <!-- Floating User Actions Dropdown -->
    <Teleport to="body">
      <div v-if="menuTarget" @click.stop :style="dropdownStyle" class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-[100005] py-1 font-mono text-xs divide-y divide-gray-800 select-none">
        <div class="py-0.5">
          <button type="button" @click="openUserActivity(menuTarget.user || menuTarget.name); menuTarget = null" class="w-full px-3 py-1.5 text-left text-cyan-300 hover:bg-cyan-950/80 cursor-pointer">View Activity</button>
          <button
            v-for="s in (menuTarget.sessions || []).filter(x => x.tty)"
            :key="s.tty"
            type="button"
            :disabled="!isOnline"
            @click="$emit('terminate-ssh', menuTarget.user || menuTarget.name, s.tty); menuTarget = null"
            class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Terminate ({{ s.tty }})
          </button>
        </div>
        <div class="py-0.5">
          <template v-if="!isProtectedUser(menuTarget)">
            <button v-if="menuTarget.is_locked" type="button" :disabled="!isOnline" @click="emitUserAction('user_unlock', menuTarget.user || menuTarget.name)" class="w-full px-3 py-1.5 text-left text-emerald-300 hover:bg-emerald-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Unlock Account</button>
            <button v-else type="button" :disabled="!isOnline" @click="emitUserAction('user_lock', menuTarget.user || menuTarget.name)" class="w-full px-3 py-1.5 text-left text-amber-300 hover:bg-amber-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Lock Account</button>
            <button type="button" :disabled="!isOnline" @click="emitUserAction('user_delete', menuTarget.user || menuTarget.name)" class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">Delete Account</button>
          </template>
          <div v-else class="px-3 py-1.5 text-[11px] text-gray-500">Protected System Account</div>
        </div>
      </div>
    </Teleport>

    <UserActivityModal
      :is-open="activityModalOpen"
      :server-id="serverId"
      :username="activityUsername"
      :account="selectedActivityAccount"
      :is-online="isOnline"
      :is-viewer="isViewer"
      @close="activityModalOpen = false"
      @terminate-ssh="(u, tty) => $emit('terminate-ssh', u, tty)"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../../i18n'
import NocTablePagination from '../../common/NocTablePagination.vue'
import UserActivityModal from '../UserActivityModal.vue'
import WorkspaceGroupsTable from './WorkspaceGroupsTable.vue'

const { t } = useI18n()
const props = defineProps({
  serverId: { type: Number, default: null },
  activeSSHSessions: { type: Array, default: () => [] },
  accountsList: { type: Array, default: () => [] },
  groupsList: { type: Array, default: () => [] },
  isOnline: { type: Boolean, default: true },
  isViewer: { type: Boolean, default: false },
})
const emit = defineEmits(['terminate-ssh', 'user-action'])

const subView = ref('users')
const userCategory = ref('all')
const userFilters = [
  { id: 'all', label: 'All' },
  { id: 'regular', label: 'Regular' },
  { id: 'system', label: 'System' },
  { id: 'active', label: 'Active' },
]

const showCreateForm = ref(false)
const createForm = ref({ username: '', password: '', shell: '/bin/bash', is_sudo: false })
const activityModalOpen = ref(false)
const activityUsername = ref('')
const selectedActivityAccount = computed(() =>
  (props.accountsList || []).find(a => (a.user || a.name) === activityUsername.value) || null
)
const search = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const menuTarget = ref(null)
const dropdownPos = ref({ top: 0, left: 0 })

watch([userCategory, search], () => { currentPage.value = 1 })

function isInteractiveShell(sh) {
  const s = String(sh || '').toLowerCase()
  return s.includes('bash') || s.includes('zsh') || s.endsWith('/sh')
}

function isProtectedUser(acc) {
  if (acc?.is_protected) return true
  const u = String(acc?.user || acc?.name || '').toLowerCase()
  return ['root', 'pantau', 'pantau-agent', 'daemon', 'bin', 'sys', 'sync', 'nobody', 'www-data', 'sshd', 'messagebus'].includes(u) || u.startsWith('systemd-')
}

const filteredAccounts = computed(() => (props.accountsList || []).filter(acc => {
  const hasAct = (acc.sessions || []).length > 0 || (acc.procs_count || 0) > 0
  if (userCategory.value === 'regular' && acc.is_system) return false
  if (userCategory.value === 'system' && !acc.is_system) return false
  if (userCategory.value === 'active' && !hasAct) return false
  if (search.value.trim()) {
    const q = search.value.toLowerCase()
    return `${acc.user || acc.name || ''} ${acc.uid ?? ''} ${acc.home || ''} ${acc.shell || ''} ${acc.group || ''}`.toLowerCase().includes(q)
  }
  return true
}))

const paginatedAccounts = computed(() => {
  if (pageSize.value === 'all') return filteredAccounts.value
  const lim = parseInt(pageSize.value, 10) || 10
  return filteredAccounts.value.slice((currentPage.value - 1) * lim, currentPage.value * lim)
})

const dropdownStyle = computed(() => ({
  position: 'fixed',
  top: `${dropdownPos.value.top}px`,
  left: `${dropdownPos.value.left}px`,
  width: '185px',
}))

function openMenu(acc, event) {
  if (menuTarget.value === acc) { menuTarget.value = null; return }
  const rect = event.currentTarget.getBoundingClientRect()
  dropdownPos.value = {
    top: Math.min(rect.bottom + 4, window.innerHeight - 170),
    left: Math.max(8, Math.min(rect.right - 185, window.innerWidth - 193)),
  }
  menuTarget.value = acc
}

function openUserActivity(username) {
  if (!username) return
  activityUsername.value = username
  activityModalOpen.value = true
}

function emitUserAction(action, username) {
  menuTarget.value = null
  emit('user-action', { action, params: { username } })
}

function submitCreateUser() {
  if (!createForm.value.username.trim() || !createForm.value.password) return
  emit('user-action', { action: 'user_create', params: { ...createForm.value, username: createForm.value.username.trim().toLowerCase() } })
  createForm.value = { username: '', password: '', shell: '/bin/bash', is_sudo: false }
  showCreateForm.value = false
}

const closeMenu = () => { menuTarget.value = null }
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>
