<template>
  <div class="space-y-6">
    <!-- Section Header -->
    <div class="border-b border-gray-800 pb-4">
      <h2 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
        <span>// {{ t('settings_title') }}</span>
      </h2>
      <p class="text-xs text-gray-400 font-mono mt-1">
        {{ t('settings_subtitle') }}
      </p>
    </div>

    <!-- Alert / Flash Message Banner -->
    <div
      v-if="flashMsg"
      class="p-3 rounded-lg border text-xs font-mono flex items-center justify-between"
      :class="flashType === 'success' ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300' : 'bg-rose-950/60 border-rose-800 text-rose-300'"
    >
      <span>{{ flashMsg }}</span>
      <button @click="flashMsg = ''" class="text-gray-400 hover:text-white font-bold ml-2 cursor-pointer">&times;</button>
    </div>

    <!-- Operator Profile & Self Password Change Card -->
    <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-lg bg-cyan-950 border border-cyan-700/50 flex items-center justify-center text-cyan-400">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-gray-100 font-mono">{{ profile?.username || 'Operator' }}</span>
              <span
                class="text-[10px] font-bold font-mono px-2 py-0.5 rounded uppercase"
                :class="profile?.is_master_admin ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-gray-800 text-gray-300 border border-gray-700'"
              >
                {{ profile?.is_master_admin ? t('settings_role_master_admin') : profile?.role }}
              </span>
            </div>
            <div class="text-[11px] text-gray-400 font-mono mt-0.5">
              {{ t('settings_col_last_login') }}: {{ formatTime(profile?.last_login_at) }}
            </div>
          </div>
        </div>

        <button
          @click="showChangePwd = !showChangePwd"
          class="px-3 py-1.5 rounded bg-gray-900/80 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-xs font-mono text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1.5"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          <span>{{ t('settings_change_pwd_btn') }}</span>
          <span class="text-[10px]">{{ showChangePwd ? '▲' : '▼' }}</span>
        </button>
      </div>

      <!-- Expandable Self Password Change Form -->
      <div v-if="showChangePwd" class="mt-4 pt-4 border-t border-gray-800/80">
        <form @submit.prevent="handleSelfPasswordChange" class="space-y-3 max-w-md">
          <div>
            <label class="block text-xs font-mono text-gray-400 mb-1">{{ t('settings_current_pwd') }}</label>
            <input
              v-model="pwdForm.current_password"
              type="password"
              required
              class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-3 py-1.5 font-mono focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-mono text-gray-400 mb-1">{{ t('settings_new_pwd') }}</label>
              <input
                v-model="pwdForm.new_password"
                type="password"
                required
                minlength="8"
                class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-3 py-1.5 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label class="block text-xs font-mono text-gray-400 mb-1">{{ t('settings_confirm_pwd') }}</label>
              <input
                v-model="pwdForm.confirm_password"
                type="password"
                required
                minlength="8"
                class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-3 py-1.5 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
          <p class="text-[10px] text-gray-400 font-mono">{{ t('settings_pwd_requirement') }}</p>
          <button
            type="submit"
            :disabled="pwdLoading"
            class="px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer"
          >
            {{ pwdLoading ? t('login_verifying') : t('settings_change_pwd_btn') }}
          </button>
        </form>
      </div>
    </div>

    <!-- User Accounts & Authority Directory (RBAC) -->
    <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative space-y-4">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>// {{ t('settings_users_title') }}</span>
          </h3>
          <p class="text-xs text-gray-400 font-mono mt-0.5">
            {{ t('settings_users_subtitle') }}
          </p>
        </div>

        <button
          @click="showAddModal = true"
          class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold transition cursor-pointer flex items-center gap-1.5 shadow-sm"
        >
          <span>+</span>
          <span>{{ t('settings_add_user_btn') }}</span>
        </button>
      </div>

      <!-- User Stats KPI Strip -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
        <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
          <div class="text-[10px] text-gray-400 uppercase font-semibold">Total Users</div>
          <div class="text-base font-extrabold text-gray-100 mt-0.5">{{ users.length }}</div>
        </div>
        <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
          <div class="text-[10px] text-cyan-400 uppercase font-semibold">Master Admin</div>
          <div class="text-base font-extrabold text-cyan-300 mt-0.5">{{ users.filter(u => u.role === 'master_admin').length }}</div>
        </div>
        <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
          <div class="text-[10px] text-emerald-400 uppercase font-semibold">Operators</div>
          <div class="text-base font-extrabold text-emerald-300 mt-0.5">{{ users.filter(u => u.role.includes('operator')).length }}</div>
        </div>
        <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
          <div class="text-[10px] text-amber-400 uppercase font-semibold">Viewers</div>
          <div class="text-base font-extrabold text-amber-300 mt-0.5">{{ users.filter(u => u.role === 'viewer').length }}</div>
        </div>
      </div>

      <!-- Users Table -->
      <div class="overflow-x-auto border border-gray-800/80 rounded-lg">
        <table class="w-full text-left font-mono border-collapse">
          <thead>
            <tr class="bg-[#0b1220] border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
              <th class="py-2.5 px-3 w-10 text-center">{{ t('settings_col_num') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_username') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_role') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_permissions') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_scope') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_status') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_last_login') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('settings_col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/60 text-xs">
            <tr
              v-for="(u, idx) in users"
              :key="u.id"
              class="hover:bg-gray-800/20 transition-colors"
            >
              <td class="py-2.5 px-3 text-center text-gray-400">{{ idx + 1 }}</td>
              <td class="py-2.5 px-3 font-bold text-gray-100 flex items-center gap-1.5">
                <span
                  class="w-1.5 h-1.5 rounded-full"
                  :class="u.is_active ? 'bg-emerald-400' : 'bg-rose-500'"
                ></span>
                <span>{{ u.username }}</span>
                <span v-if="u.id === profile?.id" class="text-[10px] text-cyan-400 font-normal">({{ t('settings_user_you') }})</span>
              </td>
              <td class="py-2.5 px-3">
                <span
                  class="text-[10px] font-bold px-1.5 py-0.5 rounded uppercase"
                  :class="getRoleClass(u.role)"
                >
                  {{ u.role === 'master_admin' ? t('settings_role_master_admin') : (u.role === 'operator' ? t('settings_role_operator') : t('settings_role_viewer')) }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-[11px]">
                <span v-if="u.role === 'master_admin'" class="text-cyan-400 font-semibold">16 / 16 (Full)</span>
                <span v-else-if="u.role === 'operator'" class="text-gray-300">
                  {{ countPerms(u.permissions) }} / 16
                </span>
                <span v-else class="text-gray-400">Read-Only</span>
              </td>
              <td class="py-2.5 px-3 text-[11px]">
                <span v-if="!u.allowed_server_ids || u.allowed_server_ids.length === 0" class="text-emerald-400 font-semibold">
                  {{ t('settings_scope_global') }}
                </span>
                <span v-else class="text-amber-400 font-semibold">
                  {{ u.allowed_server_ids.length }} Server(s)
                </span>
              </td>
              <td class="py-2.5 px-3">
                <span
                  class="text-[10px] font-bold px-1.5 py-0.5 rounded"
                  :class="u.is_active ? 'bg-emerald-950/70 text-emerald-300 border border-emerald-800/60' : 'bg-rose-950/70 text-rose-300 border border-rose-800/60'"
                >
                  {{ u.is_active ? t('settings_status_active') : t('settings_status_disabled') }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-[11px] text-gray-400">
                {{ formatTime(u.last_login_at) }}
              </td>
              <td class="py-2.5 px-3 text-right">
                <div class="inline-flex items-center gap-1.5 justify-end">
                  <!-- Edit User Button -->
                  <button
                    @click="openEditModal(u)"
                    class="p-1 rounded text-cyan-400 hover:text-white hover:bg-cyan-950/60 border border-transparent hover:border-cyan-800/50 transition cursor-pointer"
                    :title="t('settings_action_edit')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                    </svg>
                  </button>

                  <!-- Reset Password Button -->
                  <button
                    @click="openResetModal(u)"
                    class="p-1 rounded text-amber-400 hover:text-white hover:bg-amber-950/60 border border-transparent hover:border-amber-800/50 transition cursor-pointer"
                    :title="t('settings_action_reset')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                  </button>

                  <!-- Toggle Active Status Button -->
                  <button
                    v-if="u.role !== 'master_admin' && u.id !== profile?.id"
                    @click="toggleUserStatus(u)"
                    class="p-1 rounded text-gray-400 hover:text-amber-300 hover:bg-amber-950/40 transition cursor-pointer"
                    :title="u.is_active ? t('settings_action_disable') : t('settings_action_enable')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                    </svg>
                  </button>

                  <!-- Delete User Button -->
                  <button
                    v-if="u.role !== 'master_admin' && u.id !== profile?.id"
                    @click="deleteUser(u)"
                    class="p-1 rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
                    :title="t('settings_action_delete')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M3 6h18" />
                      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modals -->
    <AddUserModal
      v-if="showAddModal"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showAddModal = false"
      @created="onUserCreated"
    />

    <EditUserModal
      v-if="showEditModal && editingUser"
      :user="editingUser"
      :current-user-id="profile?.id"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showEditModal = false"
      @updated="onUserUpdated"
    />

    <ResetPasswordModal
      v-if="showResetModal && targetResetUser"
      :user="targetResetUser"
      @close="showResetModal = false"
      @reset="onPasswordReset"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from '../../i18n'
import AddUserModal from './modals/AddUserModal.vue'
import EditUserModal from './modals/EditUserModal.vue'
import ResetPasswordModal from './modals/ResetPasswordModal.vue'

const { t } = useI18n()

const profile = ref(null)
const users = ref([])
const permissionsMeta = ref({})
const serversList = ref([])

const flashMsg = ref('')
const flashType = ref('success')

const showChangePwd = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const showAddModal = ref(false)
const showEditModal = ref(false)
const editingUser = ref(null)

const showResetModal = ref(false)
const targetResetUser = ref(null)

onMounted(async () => {
  await Promise.all([
    fetchProfile(),
    fetchUsers(),
    fetchMetadata()
  ])
})

async function fetchProfile() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/me', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (res.ok) {
      profile.value = await res.json()
    }
  } catch (err) {
    console.error('Fetch profile err:', err)
  }
}

async function fetchUsers() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (res.ok) {
      users.value = await res.json()
    }
  } catch (err) {
    console.error('Fetch users err:', err)
  }
}

async function fetchMetadata() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/meta/metadata', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (res.ok) {
      const data = await res.json()
      permissionsMeta.value = data.permissions || {}
      serversList.value = data.servers || []
    }
  } catch (err) {
    console.error('Fetch metadata err:', err)
  }
}

function countPerms(perms) {
  if (!perms) return 0
  return Object.values(perms).filter(Boolean).length
}

function getRoleClass(role) {
  if (role === 'master_admin') return 'bg-cyan-950 text-cyan-300 border border-cyan-800'
  if (role === 'operator') return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  return 'bg-amber-950 text-amber-300 border border-amber-800'
}

function formatTime(isoStr) {
  if (!isoStr) return t('settings_never_logged_in')
  try {
    const d = new Date(isoStr)
    return d.toLocaleString()
  } catch {
    return isoStr
  }
}

async function handleSelfPasswordChange() {
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    flashType.value = 'error'
    flashMsg.value = t('settings_pwd_mismatch')
    return
  }

  pwdLoading.value = true
  flashMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/me/password', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        current_password: pwdForm.current_password,
        new_password: pwdForm.new_password
      })
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to update password')
    }
    flashType.value = 'success'
    flashMsg.value = t('settings_pwd_changed_success')
    pwdForm.current_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
    showChangePwd.value = false
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  } finally {
    pwdLoading.value = false
  }
}

function openEditModal(user) {
  editingUser.value = user
  showEditModal.value = true
}

function onUserUpdated(updatedUser) {
  showEditModal.value = false
  flashType.value = 'success'
  flashMsg.value = t('settings_user_updated_success', { user: updatedUser.username })
  fetchUsers()
}

function onUserCreated(createdUser) {
  showAddModal.value = false
  flashType.value = 'success'
  flashMsg.value = t('settings_user_created_success', { user: createdUser.username })
  fetchUsers()
}

function openResetModal(user) {
  targetResetUser.value = user
  showResetModal.value = true
}

function onPasswordReset(data) {
  showResetModal.value = false
  flashType.value = 'success'
  flashMsg.value = t('settings_user_reset_success', { user: targetResetUser.value?.username })
  fetchUsers()
}

async function toggleUserStatus(u) {
  const nextStatus = u.is_active ? 0 : 1
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${u.id}/status`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ is_active: nextStatus })
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to update user status')
    }
    flashType.value = 'success'
    flashMsg.value = t('settings_user_status_success')
    fetchUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}

async function deleteUser(u) {
  if (!confirm(t('settings_delete_confirm', { user: u.username }))) {
    return
  }
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${u.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to delete user')
    }
    flashType.value = 'success'
    flashMsg.value = t('settings_user_deleted_success', { user: u.username })
    fetchUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}
</script>
