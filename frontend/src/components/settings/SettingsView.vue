<template>
  <div class="space-y-6">
    <!-- 1. Header Banner -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// {{ t('settings_title') }}</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('settings_subtitle') }}
        </p>
      </div>
    </div>

    <!-- 2. Profile & Self-Service Password Security -->
    <div class="hud-tactical-card p-4 sm:p-5 rounded-xl font-mono text-xs shadow-lg space-y-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-cyan-500/20 gap-3">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-lg bg-cyan-950/80 border border-cyan-400/50 flex items-center justify-center text-cyan-300 font-bold shadow-[0_0_10px_rgba(56,189,248,0.25)] shrink-0">
            <svg class="w-5 h-5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-gray-100">{{ profile?.username || '-' }}</span>
              <span
                class="px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                :class="profile?.is_master_admin ? 'bg-cyan-950 text-cyan-300 border border-cyan-600/60' : 'bg-emerald-950 text-emerald-300 border border-emerald-600/60'"
              >
                {{ formatRole(profile?.role) }}
              </span>
            </div>
            <div class="text-[11px] text-gray-400 mt-0.5 flex items-center gap-2">
              <span>{{ t('settings_col_last_login') }}: {{ formatTimestamp(profile?.last_login_at) }}</span>
            </div>
          </div>
        </div>

        <button
          @click="showPasswordForm = !showPasswordForm"
          class="px-3 py-1.5 rounded text-xs font-semibold bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-600/50 transition cursor-pointer flex items-center gap-2 self-start sm:self-auto"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span>{{ t('settings_change_pwd_btn') }}</span>
          <svg class="w-3 h-3 transition-transform" :class="{ 'rotate-180': showPasswordForm }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
      </div>

      <!-- Change Password Form Drawer -->
      <div v-if="showPasswordForm" class="pt-2 max-w-xl space-y-3">
        <div v-if="pwdSuccessMsg" class="p-2.5 rounded bg-emerald-950/80 border border-emerald-500/60 text-emerald-300 text-xs flex items-center gap-2">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          <span>{{ pwdSuccessMsg }}</span>
        </div>
        <div v-if="pwdErrorMsg" class="p-2.5 rounded bg-rose-950/80 border border-rose-500/60 text-rose-300 text-xs flex items-center gap-2">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span>{{ pwdErrorMsg }}</span>
        </div>

        <form @submit.prevent="submitChangePassword" class="space-y-3">
          <div>
            <label class="block text-gray-300 text-xs mb-1">{{ t('settings_current_pwd') }}</label>
            <input
              v-model="pwdForm.current_password"
              type="password"
              required
              class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
            />
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-300 text-xs mb-1">{{ t('settings_new_pwd') }}</label>
              <input
                v-model="pwdForm.new_password"
                type="password"
                required
                class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
              />
            </div>
            <div>
              <label class="block text-gray-300 text-xs mb-1">{{ t('settings_confirm_pwd') }}</label>
              <input
                v-model="pwdForm.confirm_password"
                type="password"
                required
                class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
              />
            </div>
          </div>
          <p class="text-[11px] text-gray-400">{{ t('settings_pwd_requirement') }}</p>

          <button
            type="submit"
            :disabled="pwdLoading"
            class="px-4 py-2 rounded text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="pwdLoading" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
            <span>{{ t('settings_change_pwd_btn') }}</span>
          </button>
        </form>
      </div>
    </div>

    <!-- 3. User Accounts & Authority Directory (RBAC) -->
    <div v-if="canManageUsers" class="hud-tactical-card p-4 sm:p-5 rounded-xl font-mono text-xs shadow-lg space-y-4">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Title & Action Bar -->
      <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-cyan-500/20 gap-3">
        <div>
          <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
            <span>// {{ t('settings_users_title') }}</span>
          </h3>
          <p class="text-[11px] text-gray-400 mt-0.5">
            {{ t('settings_users_subtitle') }}
          </p>
        </div>

        <button
          @click="openAddUserModal"
          class="px-3 py-1.5 rounded text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white transition cursor-pointer flex items-center gap-1.5 self-start sm:self-auto shadow-[0_0_10px_rgba(56,189,248,0.25)]"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>{{ t('settings_add_user_btn') }}</span>
        </button>
      </div>

      <!-- Stats Chips -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
        <div class="bg-[#050811] border border-cyan-900/40 rounded p-2">
          <div class="text-[10px] text-gray-400 uppercase">Total Users</div>
          <div class="text-base font-bold text-gray-100 mt-0.5">{{ usersList.length }}</div>
        </div>
        <div class="bg-[#050811] border border-cyan-900/40 rounded p-2">
          <div class="text-[10px] text-gray-400 uppercase">Master Admin</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">{{ countUsersByRole('master_admin') }}</div>
        </div>
        <div class="bg-[#050811] border border-cyan-900/40 rounded p-2">
          <div class="text-[10px] text-gray-400 uppercase">Operators</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">{{ countUsersByRole('operator') }}</div>
        </div>
        <div class="bg-[#050811] border border-cyan-900/40 rounded p-2">
          <div class="text-[10px] text-gray-400 uppercase">Viewers</div>
          <div class="text-base font-bold text-gray-300 mt-0.5">{{ countUsersByRole('viewer') }}</div>
        </div>
      </div>

      <!-- Users Data Table -->
      <div class="overflow-x-auto rounded border border-cyan-900/40">
        <table class="w-full text-left text-xs text-gray-200">
          <thead class="bg-[#050811] text-[11px] font-bold text-gray-400 uppercase border-b border-cyan-900/60">
            <tr>
              <th class="py-2.5 px-3 w-12">{{ t('settings_col_num') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_username') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_role') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_status') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_created_by') }}</th>
              <th class="py-2.5 px-3">{{ t('settings_col_last_login') }}</th>
              <th class="py-2.5 px-3 text-right">{{ t('settings_col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-cyan-950/60">
            <tr v-for="(u, idx) in usersList" :key="u.id" class="hover:bg-cyan-950/20 transition">
              <td class="py-2.5 px-3 text-gray-400">{{ idx + 1 }}</td>
              <td class="py-2.5 px-3 font-bold text-gray-100 flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full" :class="u.is_active ? 'bg-emerald-400' : 'bg-gray-600'"></span>
                <span>{{ u.username }}</span>
                <span v-if="u.id === profile?.id" class="text-[10px] text-cyan-400 font-normal">(you)</span>
              </td>
              <td class="py-2.5 px-3">
                <span
                  class="px-2 py-0.5 rounded text-[10px] font-bold uppercase"
                  :class="u.role === 'master_admin' ? 'bg-cyan-950 text-cyan-300 border border-cyan-600/60' : (u.role === 'operator' ? 'bg-emerald-950 text-emerald-300 border border-emerald-600/60' : 'bg-gray-800 text-gray-300 border border-gray-600/50')"
                >
                  {{ formatRole(u.role) }}
                </span>
              </td>
              <td class="py-2.5 px-3">
                <span
                  class="text-[11px] font-semibold"
                  :class="u.is_active ? 'text-emerald-400' : 'text-rose-400'"
                >
                  {{ u.is_active ? t('settings_status_active') : t('settings_status_disabled') }}
                </span>
              </td>
              <td class="py-2.5 px-3 text-gray-400">{{ u.created_by || 'system' }}</td>
              <td class="py-2.5 px-3 text-gray-400">{{ formatTimestamp(u.last_login_at) }}</td>
              <td class="py-2.5 px-3 text-right">
                <div class="inline-flex items-center gap-1.5">
                  <!-- Toggle Active Status Button (Tier 3 Icon Only) -->
                  <button
                    v-if="u.id !== profile?.id && u.role !== 'master_admin'"
                    @click="toggleUserStatus(u)"
                    class="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer"
                    :title="u.is_active ? 'Disable Account' : 'Activate Account'"
                  >
                    <svg v-if="u.is_active" class="w-3.5 h-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                    <svg v-else class="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                  </button>

                  <!-- Reset Password Button (Tier 3 Icon Only) -->
                  <button
                    v-if="profile?.is_master_admin || u.role !== 'master_admin'"
                    @click="openResetPasswordModal(u)"
                    class="p-1 rounded text-gray-400 hover:text-cyan-300 hover:bg-gray-800 transition cursor-pointer"
                    :title="t('settings_modal_reset_title')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                    </svg>
                  </button>

                  <!-- Delete User Button (Tier 3 Icon Only) -->
                  <button
                    v-if="u.id !== profile?.id && u.role !== 'master_admin'"
                    @click="confirmDeleteUser(u)"
                    class="p-1 rounded text-gray-400 hover:text-rose-400 hover:bg-gray-800 transition cursor-pointer"
                    title="Delete User"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 4. Operational Thresholds & Security Policies -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
      <div class="hud-tactical-card p-4 rounded-xl space-y-3 shadow-lg">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider border-b border-cyan-500/20 pb-2">
          // {{ t('rbac_title') }}
        </h3>
        <div class="text-xs text-gray-300 space-y-2.5 leading-relaxed">
          <p>
            ● <strong class="text-cyan-400">{{ t('rbac_master_admin').split(':')[0] }}:</strong> {{ t('rbac_master_admin').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-emerald-400">{{ t('rbac_full_operator').split(':')[0] }}:</strong> {{ t('rbac_full_operator').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-gray-400">{{ t('rbac_protect_accounts').split(':')[0] }}:</strong> {{ t('rbac_protect_accounts').split(':')[1] }}
          </p>
        </div>
      </div>

      <div class="hud-tactical-card p-4 rounded-xl space-y-3 shadow-lg">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider border-b border-cyan-500/20 pb-2">
          // {{ t('threshold_title') }}
        </h3>
        <div class="text-xs text-gray-300 space-y-2 leading-relaxed">
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_cpu') }}</span>
            <span class="font-bold text-rose-400 font-mono">85%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_ram') }}</span>
            <span class="font-bold text-rose-400 font-mono">90%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_ssh') }}</span>
            <span class="font-bold text-emerald-400 font-mono">{{ t('threshold_active') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 5. Modal: Add New User -->
    <div
      v-if="showAddModal"
      class="fixed inset-0 z-50 bg-black/75 backdrop-blur-[4px] flex items-center justify-center p-4"
      @click.self="showAddModal = false"
    >
      <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-cyan-500/40 font-mono text-xs">
        <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider border-b border-cyan-500/20 pb-2 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>// {{ t('settings_modal_add_title') }}</span>
        </h3>

        <div v-if="addErrorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-500/60 text-rose-300 text-[11px]">
          {{ addErrorMsg }}
        </div>

        <form @submit.prevent="submitAddUser" class="space-y-3">
          <div>
            <label class="block text-gray-300 text-xs mb-1">{{ t('settings_col_username') }}</label>
            <input
              v-model="addForm.username"
              type="text"
              required
              class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
              placeholder="e.g. operator_budiman"
            />
          </div>
          <div>
            <label class="block text-gray-300 text-xs mb-1">{{ t('settings_col_role') }}</label>
            <select
              v-model="addForm.role"
              class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
            >
              <option value="operator">{{ t('settings_role_operator') }}</option>
              <option value="viewer">{{ t('settings_role_viewer') }}</option>
            </select>
          </div>
          <div>
            <label class="block text-gray-300 text-xs mb-1">{{ t('login_password') }}</label>
            <input
              v-model="addForm.password"
              type="password"
              required
              class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
            />
            <p class="text-[10px] text-gray-400 mt-1">{{ t('settings_pwd_requirement') }}</p>
          </div>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-cyan-900/40">
            <button
              type="button"
              @click="showAddModal = false"
              class="px-3 py-1.5 rounded text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer"
            >
              {{ t('settings_btn_cancel') }}
            </button>
            <button
              type="submit"
              :disabled="addLoading"
              class="px-3.5 py-1.5 rounded text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-white cursor-pointer disabled:opacity-50"
            >
              {{ t('settings_btn_create') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 6. Modal: Reset User Password -->
    <div
      v-if="showResetModal"
      class="fixed inset-0 z-50 bg-black/75 backdrop-blur-[4px] flex items-center justify-center p-4"
      @click.self="showResetModal = false"
    >
      <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-amber-500/40 font-mono text-xs">
        <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider border-b border-amber-500/20 pb-2 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-amber-400"></span>
          <span>// {{ t('settings_modal_reset_title') }}: {{ targetUser?.username }}</span>
        </h3>

        <div v-if="resetErrorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-500/60 text-rose-300 text-[11px]">
          {{ resetErrorMsg }}
        </div>

        <form @submit.prevent="submitResetPassword" class="space-y-3">
          <div>
            <label class="block text-gray-300 text-xs mb-1">{{ t('settings_new_pwd') }}</label>
            <input
              v-model="resetForm.new_password"
              type="password"
              required
              class="w-full bg-[#050811] border border-cyan-900/60 rounded px-3 py-2 text-gray-200 text-xs focus:border-cyan-400 focus:outline-none"
            />
            <p class="text-[10px] text-gray-400 mt-1">{{ t('settings_pwd_requirement') }}</p>
          </div>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-cyan-900/40">
            <button
              type="button"
              @click="showResetModal = false"
              class="px-3 py-1.5 rounded text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer"
            >
              {{ t('settings_btn_cancel') }}
            </button>
            <button
              type="submit"
              :disabled="resetLoading"
              class="px-3.5 py-1.5 rounded text-xs font-bold bg-amber-600 hover:bg-amber-500 text-black cursor-pointer disabled:opacity-50"
            >
              {{ t('settings_btn_reset') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '../../i18n'

const { t } = useI18n()

const profile = ref(null)
const usersList = ref([])
const showPasswordForm = ref(false)
const pwdLoading = ref(false)
const pwdSuccessMsg = ref('')
const pwdErrorMsg = ref('')

const pwdForm = ref({
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const showAddModal = ref(false)
const addLoading = ref(false)
const addErrorMsg = ref('')
const addForm = ref({
  username: '',
  role: 'operator',
  password: ''
})

const showResetModal = ref(false)
const resetLoading = ref(false)
const resetErrorMsg = ref('')
const targetUser = ref(null)
const resetForm = ref({
  new_password: ''
})

const canManageUsers = computed(() => {
  return profile.value?.is_master_admin || profile.value?.role === 'master_admin'
})

function formatRole(role) {
  if (!role) return '-'
  if (role.includes('admin')) return t('settings_role_master_admin')
  if (role.includes('operator')) return t('settings_role_operator')
  return t('settings_role_viewer')
}

function formatTimestamp(ts) {
  if (!ts) return t('settings_never_logged_in')
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch (e) {
    return String(ts)
  }
}

function countUsersByRole(roleKey) {
  return usersList.value.filter(u => u.role.includes(roleKey)).length
}

function getAuthHeaders() {
  const token = localStorage.getItem('pantau_token') || ''
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  }
}

async function loadProfile() {
  try {
    const res = await fetch('/api/users/me', { headers: getAuthHeaders() })
    if (res.ok) {
      profile.value = await res.json()
    }
  } catch (err) {
    console.error('Failed to load user profile:', err)
  }
}

async function loadUsers() {
  if (!canManageUsers.value) return
  try {
    const res = await fetch('/api/users', { headers: getAuthHeaders() })
    if (res.ok) {
      usersList.value = await res.json()
    }
  } catch (err) {
    console.error('Failed to load users list:', err)
  }
}

async function submitChangePassword() {
  pwdErrorMsg.value = ''
  pwdSuccessMsg.value = ''

  if (pwdForm.value.new_password !== pwdForm.value.confirm_password) {
    pwdErrorMsg.value = t('settings_pwd_mismatch')
    return
  }

  pwdLoading.value = true
  try {
    const res = await fetch('/api/users/me/password', {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        current_password: pwdForm.value.current_password,
        new_password: pwdForm.value.new_password
      })
    })
    const data = await res.json()
    if (!res.ok) {
      pwdErrorMsg.value = data.detail || 'Failed to update password.'
    } else {
      pwdSuccessMsg.value = t('settings_pwd_changed_success')
      pwdForm.value.current_password = ''
      pwdForm.value.new_password = ''
      pwdForm.value.confirm_password = ''
      setTimeout(() => { showPasswordForm.value = false }, 2000)
    }
  } catch (err) {
    pwdErrorMsg.value = err.message || 'Connection error'
  } finally {
    pwdLoading.value = false
  }
}

function openAddUserModal() {
  addErrorMsg.value = ''
  addForm.value = { username: '', role: 'operator', password: '' }
  showAddModal.value = true
}

async function submitAddUser() {
  addErrorMsg.value = ''
  addLoading.value = true
  try {
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(addForm.value)
    })
    const data = await res.json()
    if (!res.ok) {
      addErrorMsg.value = data.detail || 'Failed to create user.'
    } else {
      showAddModal.value = false
      await loadUsers()
    }
  } catch (err) {
    addErrorMsg.value = err.message || 'Connection error'
  } finally {
    addLoading.value = false
  }
}

async function toggleUserStatus(u) {
  const nextStatus = u.is_active ? 0 : 1
  try {
    const res = await fetch(`/api/users/${u.id}/status`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({ is_active: nextStatus })
    })
    if (res.ok) {
      await loadUsers()
    }
  } catch (err) {
    console.error('Failed to toggle status:', err)
  }
}

function openResetPasswordModal(u) {
  targetUser.value = u
  resetErrorMsg.value = ''
  resetForm.value = { new_password: '' }
  showResetModal.value = true
}

async function submitResetPassword() {
  if (!targetUser.value) return
  resetErrorMsg.value = ''
  resetLoading.value = true
  try {
    const res = await fetch(`/api/users/${targetUser.value.id}/reset-password`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify(resetForm.value)
    })
    const data = await res.json()
    if (!res.ok) {
      resetErrorMsg.value = data.detail || 'Failed to reset password.'
    } else {
      showResetModal.value = false
    }
  } catch (err) {
    resetErrorMsg.value = err.message || 'Connection error'
  } finally {
    resetLoading.value = false
  }
}

async function confirmDeleteUser(u) {
  if (!confirm(t('settings_delete_confirm', { user: u.username }))) return
  try {
    const res = await fetch(`/api/users/${u.id}`, {
      method: 'DELETE',
      headers: getAuthHeaders()
    })
    if (res.ok) {
      await loadUsers()
    }
  } catch (err) {
    console.error('Failed to delete user:', err)
  }
}

onMounted(async () => {
  await loadProfile()
  await loadUsers()
})
</script>
