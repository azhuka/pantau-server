<template>
  <div class="space-y-6">
    <!-- Header & Sub-Tab Navigation -->
    <div class="border-b border-gray-800 pb-4 flex items-center justify-between flex-wrap gap-4">
      <div>
        <h2 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// {{ activeTab === 'rbac' ? t('settings_title') : t('settings_subtab_master_control') }}</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-1">
          {{ activeTab === 'rbac' ? t('settings_header_desc_rbac') : t('settings_header_desc_mc') }}
        </p>
      </div>

      <!-- Sub-Tab Switcher Buttons -->
      <div class="flex items-center gap-1.5 p-1 bg-[#090e1c] border border-gray-800 rounded-lg font-mono text-xs">
        <button
          @click="activeTab = 'rbac'"
          class="px-3 py-1.5 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
          :class="activeTab === 'rbac' ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow-sm' : 'text-gray-400 hover:text-gray-200'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <span>{{ t('settings_subtab_rbac') }}</span>
        </button>
        <button
          @click="activeTab = 'master_control'"
          class="px-3 py-1.5 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
          :class="activeTab === 'master_control' ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow-sm' : 'text-gray-400 hover:text-gray-200'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          <span>{{ t('settings_subtab_master_control') }}</span>
        </button>
      </div>
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

    <!-- TAB 1: OTORITAS & MANAJEMEN PENGGUNA (RBAC) -->
    <div v-if="activeTab === 'rbac'" class="space-y-6">
      <!-- Top Cards Grid: Panel 1 Profile + Panel 2 2FA -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Panel 1: Profile & Credentials Edit -->
        <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative flex flex-col justify-between font-mono">
          <div>
            <div class="flex items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800/80">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-cyan-950 border border-cyan-700/50 flex items-center justify-center text-cyan-400">
                  <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-bold text-gray-100">{{ profile?.username || 'Operator' }}</span>
                    <span
                      class="text-[10px] font-bold px-2 py-0.5 rounded uppercase"
                      :class="profile?.is_master_admin ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-gray-800 text-gray-300 border border-gray-700'"
                    >
                      {{ profile?.is_master_admin ? 'Master Admin' : profile?.role }}
                    </span>
                  </div>
                  <div class="text-[11px] text-gray-400 mt-0.5">
                    {{ t('settings_col_last_login') }}: {{ formatTime(profile?.last_login_at) }}
                  </div>
                </div>
              </div>

              <!-- Button Edit Profile (Tier 2: Icon + Label) -->
              <button
                v-if="profile"
                @click="showEditSelfModal = true"
                class="px-3 py-1.5 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-xs text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1.5 font-bold shadow-sm"
                :title="t('settings_btn_edit')"
              >
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
                <span>{{ t('settings_btn_edit') || 'Edit' }}</span>
              </button>
            </div>

            <!-- Profile Details Summary -->
            <div class="mt-3 space-y-1.5 text-xs text-gray-300">
              <div class="flex justify-between items-center py-0.5">
                <span class="text-gray-400">{{ t('settings_col_status') }}:</span>
                <span class="text-emerald-400 font-bold flex items-center gap-1">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  <span>{{ t('settings_status_active') }}</span>
                </span>
              </div>
              <div class="flex justify-between items-center py-0.5">
                <span class="text-gray-400">{{ t('settings_password_changed_at') || 'Password Changed:' }}</span>
                <span class="text-gray-300 font-mono text-[11px]">
                  {{ profile?.password_changed_at ? formatTime(profile.password_changed_at) : (t('settings_never_changed') || 'Never') }}
                </span>
              </div>
              <div v-if="profile?.role === 'operator'" class="pt-2 border-t border-gray-800/60">
                <div class="text-[11px] font-bold text-cyan-400 mb-1">// Active Permissions:</div>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="(val, k) in profile?.permissions || {}"
                    :key="k"
                    v-show="val"
                    class="px-1.5 py-0.5 rounded text-[9.5px] bg-cyan-950 text-cyan-300 border border-cyan-800/80 font-bold"
                  >
                    ✔ {{ t('perm_' + k) || k }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Panel 2: 2FA / TOTP Security -->
        <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative flex flex-col justify-between font-mono">
          <div>
            <div class="flex items-center justify-between pb-3 border-b border-gray-800/80">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-lg bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </div>
                <div>
                  <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">
                    {{ t('settings_2fa_title') }}
                  </h3>
                  <p class="text-[10px] text-gray-400">{{ t('settings_2fa_standard') }}</p>
                </div>
              </div>

              <span
                class="text-[10px] font-bold px-2 py-0.5 rounded"
                :class="profile?.totp_enabled ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'"
              >
                {{ profile?.totp_enabled ? t('settings_2fa_active_badge') : t('settings_2fa_disabled_badge') }}
              </span>
            </div>

            <p class="text-xs text-gray-300 mt-3 leading-relaxed">
              {{ profile?.totp_enabled ? t('settings_2fa_enabled_desc') : t('settings_2fa_disabled_desc') }}
            </p>

            <!-- 2FA Active: Recovery Codes Counter Box -->
            <div v-if="profile?.totp_enabled" class="mt-2.5 p-2 rounded bg-[#0c1424] border border-cyan-900/50 flex items-center justify-between text-xs">
              <span class="text-gray-400">Backup Recovery Codes:</span>
              <span class="font-bold text-cyan-300">{{ t('settings_2fa_recovery_codes_left', { count: profile?.recovery_codes_count ?? 8 }) }}</span>
            </div>
          </div>

          <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center justify-between flex-wrap gap-2">
            <span class="text-[11px] text-gray-400">
              {{ profile?.totp_enabled ? t('settings_2fa_status_protected') : t('settings_2fa_status_unprotected') }}
            </span>

            <div class="flex items-center gap-2">
              <template v-if="!profile?.totp_enabled">
                <button
                  @click="showSetup2faModal = true"
                  class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition cursor-pointer flex items-center gap-1.5"
                >
                  <span>{{ t('settings_2fa_enable_btn') }}</span>
                </button>
              </template>
              <template v-else>
                <button
                  type="button"
                  @click="handleRegenerateRecoveryCodes"
                  class="px-2.5 py-1.5 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 text-xs font-bold transition cursor-pointer"
                  :title="t('settings_2fa_btn_regenerate')"
                >
                  {{ t('settings_2fa_btn_regenerate') || 'Regenerate Codes' }}
                </button>
                <button
                  type="button"
                  @click="handleDisableOwn2fa"
                  class="px-3 py-1.5 rounded bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-bold transition cursor-pointer"
                >
                  <span>{{ t('settings_2fa_disable_btn') }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Section 3: Full-Width Streamlined User Accounts Directory (RBAC) -->
      <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative space-y-4 font-mono">
        <!-- Directory Header with Add User Button in Toolbar -->
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
              <span>// {{ t('settings_users_title') }}</span>
            </h3>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ t('settings_dir_desc') }}
            </p>
          </div>

          <div class="flex items-center gap-2">
            <span class="text-xs px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
              {{ users.length }} accounts
            </span>

            <!-- Uniform Modal Trigger: + Tambah Pengguna -->
            <button
              v-if="profile?.is_master_admin || profile?.permissions?.can_manage_users"
              @click="showAddModal = true"
              class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shadow-sm"
              :title="t('settings_add_user_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              <span>{{ t('settings_add_user_btn') || 'Tambah Pengguna' }}</span>
            </button>
          </div>
        </div>

        <!-- KPI Strip -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-gray-400 uppercase font-semibold">{{ t('settings_kpi_total') }}</div>
            <div class="text-base font-extrabold text-gray-100 mt-0.5">{{ users.length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-cyan-400 uppercase font-semibold">{{ t('settings_kpi_master') }}</div>
            <div class="text-base font-extrabold text-cyan-300 mt-0.5">{{ users.filter(u => u.role === 'master_admin').length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-emerald-400 uppercase font-semibold">{{ t('settings_kpi_operator') }}</div>
            <div class="text-base font-extrabold text-emerald-300 mt-0.5">{{ users.filter(u => u.role === 'operator').length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-amber-400 uppercase font-semibold">{{ t('settings_kpi_viewer') }}</div>
            <div class="text-base font-extrabold text-amber-300 mt-0.5">{{ users.filter(u => u.role === 'viewer').length }}</div>
          </div>
        </div>

        <!-- Filter & Search Toolbar -->
        <div class="flex items-center justify-between flex-wrap gap-2.5 pt-2 border-t border-gray-800/80 text-xs">
          <div class="flex items-center gap-2 flex-wrap flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-gray-400 text-[11px]">{{ t('settings_filter_role') }}</span>
              <select
                v-model="userRoleFilter"
                class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
              >
                <option value="">{{ t('settings_all_roles') }}</option>
                <option value="master_admin">{{ t('settings_role_master_admin') }}</option>
                <option value="operator">{{ t('settings_role_operator') }}</option>
                <option value="viewer">{{ t('settings_role_viewer') }}</option>
              </select>
            </div>

            <div class="flex items-center gap-1.5">
              <span class="text-gray-400 text-[11px]">{{ t('settings_filter_status') }}</span>
              <select
                v-model="userStatusFilter"
                class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
              >
                <option value="">{{ t('settings_all_status') }}</option>
                <option value="active">{{ t('settings_status_active') }}</option>
                <option value="disabled">{{ t('settings_status_disabled') }}</option>
              </select>
            </div>
          </div>

          <div class="w-full sm:w-64">
            <input
              v-model="userSearchQuery"
              type="search"
              :placeholder="t('settings_search_placeholder')"
              class="w-full bg-[#111827] border border-gray-800 rounded px-3 py-1 text-xs text-gray-200 focus:border-cyan-500 outline-none"
            />
          </div>
        </div>

        <!-- Users Table -->
        <div class="overflow-x-auto border border-gray-800/80 rounded-lg">
          <table class="w-full text-left border-collapse text-xs">
            <thead>
              <tr class="bg-[#0b1220] border-b border-gray-800 text-[11px] text-gray-400 uppercase font-bold tracking-wider">
                <th class="py-2.5 px-3 w-10 text-center">{{ t('settings_col_num') }}</th>
                <th class="py-2.5 px-3">{{ t('settings_col_username') }}</th>
                <th class="py-2.5 px-3">{{ t('settings_col_role') }}</th>
                <th class="py-2.5 px-3">{{ t('settings_col_status') }}</th>
                <th class="py-2.5 px-3">{{ t('settings_col_last_login') }}</th>
                <th class="py-2.5 px-3 text-right">{{ t('settings_col_actions') }}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-800/60">
              <tr
                v-for="(u, idx) in filteredUsers"
                :key="u.id"
                class="hover:bg-gray-800/20 transition-colors"
              >
                <td class="py-2.5 px-3 text-center text-gray-400">{{ idx + 1 }}</td>
                <td class="py-2.5 px-3">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-gray-100 text-xs">{{ u.username }}</span>
                    <span v-if="u.id === profile?.id" class="text-[10px] text-cyan-400 font-normal">{{ t('settings_you') }}</span>
                  </div>
                  <div v-if="u.role === 'operator'" class="flex items-center gap-1.5 mt-1">
                    <span class="px-1.5 py-0.5 rounded text-[9px] bg-cyan-950 text-cyan-300 border border-cyan-800/80 font-bold">
                      {{ t('settings_perms_badge', { count: countPerms(u.permissions) }) }}
                    </span>
                    <span
                      class="px-1.5 py-0.5 rounded text-[9px] font-bold"
                      :class="!u.allowed_server_ids || u.allowed_server_ids.length === 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'"
                    >
                      {{ !u.allowed_server_ids || u.allowed_server_ids.length === 0 ? t('settings_all_servers') : t('settings_scope_servers', { count: u.allowed_server_ids.length }) }}
                    </span>
                  </div>
                </td>
                <td class="py-2.5 px-3">
                  <span
                    class="text-[10px] font-bold px-2 py-0.5 rounded uppercase"
                    :class="getRoleClass(u.role)"
                  >
                    {{ u.role === 'master_admin' ? 'Master Admin' : (u.role === 'operator' ? 'Operator' : 'Viewer') }}
                  </span>
                </td>
                <td class="py-2.5 px-3">
                  <div class="flex items-center gap-2">
                    <span
                      class="text-[10px] font-bold flex items-center gap-1"
                      :class="u.is_active ? 'text-emerald-400' : 'text-rose-400'"
                    >
                      <span class="w-1.5 h-1.5 rounded-full" :class="u.is_active ? 'bg-emerald-400' : 'bg-rose-400'"></span>
                      <span>{{ u.is_active ? t('settings_status_active') : t('settings_status_disabled') }}</span>
                    </span>
                    <span class="text-gray-600">/</span>
                    <span
                      class="text-[10px]"
                      :class="u.totp_enabled ? 'text-emerald-400 font-semibold' : 'text-gray-400'"
                    >
                      {{ u.totp_enabled ? '2FA ✔' : '2FA -' }}
                    </span>
                  </div>
                </td>
                <td class="py-2.5 px-3 text-gray-400 text-[11px]">
                  {{ formatTime(u.last_login_at) }}
                </td>
                <td class="py-2.5 px-3 text-right">
                  <!-- Icon-Only Action Dropdown Trigger (3-dots vertical SVG) -->
                  <div class="relative inline-block text-left">
                    <button
                      type="button"
                      @click.stop="toggleActionDropdown(u, $event)"
                      class="p-1.5 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-300 hover:text-cyan-300 transition cursor-pointer flex items-center justify-center shadow-sm"
                      :title="t('settings_col_actions')"
                      aria-label="Actions"
                    >
                      <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="1.5"></circle>
                        <circle cx="12" cy="5" r="1.5"></circle>
                        <circle cx="12" cy="19" r="1.5"></circle>
                      </svg>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 2: MASTER CONTROL & AMBANG BATAS (THRESHOLDS) -->
    <div v-else-if="activeTab === 'master_control'">
      <MasterControlSection />
    </div>

    <!-- Modals -->
    <AddUserModal
      v-if="showAddModal"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showAddModal = false"
      @created="onUserCreated"
    />

    <EditSelfModal
      v-if="showEditSelfModal && profile"
      :user="profile"
      @close="showEditSelfModal = false"
      @updated="onProfileUpdated"
    />

    <EditPermsModal
      v-if="showEditPermsModal && targetPermsUser"
      :user="targetPermsUser"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showEditPermsModal = false"
      @updated="onUserUpdated"
    />

    <Admin2faModal
      v-if="showAdmin2faModal && targetAdmin2faUser"
      :user="targetAdmin2faUser"
      @close="showAdmin2faModal = false"
      @updated="onUserUpdated"
    />

    <Setup2faModal
      v-if="showSetup2faModal"
      @close="showSetup2faModal = false"
      @enabled="onSelf2faEnabled"
    />

    <ResetPasswordModal
      v-if="showResetModal && targetResetUser"
      :user="targetResetUser"
      @close="showResetModal = false"
      @reset="onPasswordReset"
    />

    <RecoveryCodesModal
      v-if="showRecoveryCodesModal"
      :codes="newlyGeneratedRecoveryCodes"
      @close="showRecoveryCodesModal = false"
    />

    <!-- Floating Action Dropdown Menu (Teleported to body to eliminate overflow clipping) -->
    <Teleport to="body">
      <div
        v-if="openDropdownId && activeDropdownUser"
        @click.stop
        :style="dropdownStyle"
        class="rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl py-1 text-xs divide-y divide-gray-800 transition-all select-none"
      >
        <div class="py-0.5">
          <!-- Atur Izin (Only for Operator) -->
          <button
            v-if="activeDropdownUser.role === 'operator' && (profile?.is_master_admin || profile?.permissions?.can_manage_users)"
            type="button"
            @click="openEditPermsModal(activeDropdownUser); closeDropdown()"
            class="w-full px-3 py-1.5 text-left text-cyan-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition font-bold"
          >
            <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>{{ t('settings_action_perms') || 'Atur Izin' }}</span>
          </button>

          <!-- Reset Password -->
          <button
            v-if="profile?.is_master_admin || profile?.permissions?.can_manage_users"
            type="button"
            @click="openResetModal(activeDropdownUser); closeDropdown()"
            class="w-full px-3 py-1.5 text-left text-gray-200 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
          >
            <svg class="w-3.5 h-3.5 text-yellow-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            <span>{{ t('settings_action_reset') }}</span>
          </button>

          <!-- Kelola 2FA (Admin Reset) -->
          <button
            v-if="profile?.is_master_admin && activeDropdownUser.id !== profile?.id && activeDropdownUser.totp_enabled"
            type="button"
            @click="openAdmin2faModal(activeDropdownUser); closeDropdown()"
            class="w-full px-3 py-1.5 text-left text-amber-300 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
          >
            <svg class="w-3.5 h-3.5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span>{{ t('settings_action_manage_2fa') }}</span>
          </button>
        </div>

        <div v-if="activeDropdownUser.role !== 'master_admin' && activeDropdownUser.id !== profile?.id" class="py-0.5">
          <!-- Kunci / Buka Kunci -->
          <button
            type="button"
            @click="toggleUserStatus(activeDropdownUser); closeDropdown()"
            class="w-full px-3 py-1.5 text-left flex items-center gap-2 cursor-pointer transition"
            :class="activeDropdownUser.is_active ? 'text-amber-400 hover:bg-amber-950/60' : 'text-emerald-400 hover:bg-emerald-950/60'"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
            <span>{{ activeDropdownUser.is_active ? t('settings_action_lock') : t('settings_action_unlock') }}</span>
          </button>

          <!-- Hapus Pengguna -->
          <button
            type="button"
            @click="deleteUser(activeDropdownUser); closeDropdown()"
            class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 flex items-center gap-2 cursor-pointer transition font-bold"
          >
            <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
            <span>{{ t('settings_action_delete') }}</span>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import MasterControlSection from './MasterControlSection.vue'
import AddUserModal from './modals/AddUserModal.vue'
import EditSelfModal from './modals/EditSelfModal.vue'
import EditPermsModal from './modals/EditPermsModal.vue'
import Admin2faModal from './modals/Admin2faModal.vue'
import Setup2faModal from './modals/Setup2faModal.vue'
import ResetPasswordModal from './modals/ResetPasswordModal.vue'
import RecoveryCodesModal from './modals/RecoveryCodesModal.vue'

const { t } = useI18n()
const activeTab = ref('rbac')
const profile = ref(null)
const users = ref([])
const permissionsMeta = ref({})
const serversList = ref([])

const userRoleFilter = ref('')
const userStatusFilter = ref('')
const userSearchQuery = ref('')

const openDropdownId = ref(null)
const activeDropdownUser = ref(null)
const dropdownStyle = ref({})

const showAddModal = ref(false)
const showEditSelfModal = ref(false)
const showEditPermsModal = ref(false)
const targetPermsUser = ref(null)

const showAdmin2faModal = ref(false)
const targetAdmin2faUser = ref(null)

const showSetup2faModal = ref(false)
const showRecoveryCodesModal = ref(false)
const newlyGeneratedRecoveryCodes = ref([])

const showResetModal = ref(false)
const targetResetUser = ref(null)

const flashMsg = ref('')
const flashType = ref('success')

function closeDropdown() {
  openDropdownId.value = null
  activeDropdownUser.value = null
}

function handleGlobalClick() {
  closeDropdown()
}

onMounted(() => {
  window.addEventListener('click', handleGlobalClick)
  window.addEventListener('scroll', closeDropdown, true)
  window.addEventListener('resize', closeDropdown)
  loadMetadata()
  loadProfile()
  loadUsers()
})

onUnmounted(() => {
  window.removeEventListener('click', handleGlobalClick)
  window.removeEventListener('scroll', closeDropdown, true)
  window.removeEventListener('resize', closeDropdown)
})

function toggleActionDropdown(user, event) {
  if (openDropdownId.value === user.id) {
    closeDropdown()
    return
  }
  openDropdownId.value = user.id
  activeDropdownUser.value = user

  if (event && event.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const vh = window.innerHeight
    const vw = window.innerWidth

    let itemCount = 0
    if (user.role === 'operator' && (profile.value?.is_master_admin || profile.value?.permissions?.can_manage_users)) itemCount++
    if (profile.value?.is_master_admin || profile.value?.permissions?.can_manage_users) itemCount++
    if (profile.value?.is_master_admin && user.id !== profile.value?.id && user.totp_enabled) itemCount++
    if (user.role !== 'master_admin' && user.id !== profile.value?.id) itemCount += 2
    const menuHeight = Math.max(80, itemCount * 32 + 16)

    const spaceBelow = vh - rect.bottom
    const spaceAbove = rect.top
    const isDropup = (spaceBelow < menuHeight + 10) && (spaceAbove > spaceBelow)

    const rightOffset = Math.max(8, vw - rect.right)

    if (isDropup) {
      dropdownStyle.value = {
        position: 'fixed',
        bottom: `${Math.max(8, vh - rect.top + 4)}px`,
        right: `${rightOffset}px`,
        zIndex: 100005,
        minWidth: '175px'
      }
    } else {
      dropdownStyle.value = {
        position: 'fixed',
        top: `${Math.max(8, rect.bottom + 4)}px`,
        right: `${rightOffset}px`,
        zIndex: 100005,
        minWidth: '175px'
      }
    }
  }
}

const filteredUsers = computed(() => {
  return users.value.filter((u) => {
    if (userRoleFilter.value && u.role !== userRoleFilter.value) return false
    if (userStatusFilter.value === 'active' && !u.is_active) return false
    if (userStatusFilter.value === 'disabled' && u.is_active) return false
    if (userSearchQuery.value) {
      const q = userSearchQuery.value.toLowerCase().trim()
      if (!u.username.toLowerCase().includes(q)) return false
    }
    return true
  })
})

function countPerms(perms) {
  if (!perms) return 0
  return Object.values(perms).filter(Boolean).length
}

function getRoleClass(role) {
  if (role === 'master_admin') return 'bg-cyan-950 text-cyan-300 border border-cyan-800'
  if (role === 'operator') return 'bg-emerald-950 text-emerald-300 border border-emerald-800'
  return 'bg-amber-950 text-amber-300 border border-amber-800'
}

async function loadMetadata() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/metadata', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      const data = await res.json()
      permissionsMeta.value = data.permissions || {}
      serversList.value = data.servers || []
    }
  } catch (err) {
    console.error('Failed to load user metadata:', err)
  }
}

async function loadProfile() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/profile', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      profile.value = await res.json()
    }
  } catch (err) {
    console.error('Failed to load profile:', err)
  }
}

async function loadUsers() {
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users', {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      users.value = await res.json()
    }
  } catch (err) {
    console.error('Failed to load users list:', err)
  }
}

function openEditPermsModal(user) {
  targetPermsUser.value = user
  showEditPermsModal.value = true
}

function openAdmin2faModal(user) {
  targetAdmin2faUser.value = user
  showAdmin2faModal.value = true
}

function openResetModal(user) {
  targetResetUser.value = user
  showResetModal.value = true
}

function onSelf2faEnabled() {
  loadProfile()
  loadUsers()
  flashType.value = 'success'
  flashMsg.value = 'Two-factor authentication (2FA) has been enabled for your account.'
}

async function handleRegenerateRecoveryCodes() {
  if (!confirm(t('settings_confirm_regenerate') || 'Generating new recovery codes will immediately invalidate all existing backup codes. Continue?')) {
    return
  }
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/2fa/regenerate-recovery', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      }
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to regenerate recovery codes')
    newlyGeneratedRecoveryCodes.value = data.recovery_codes || []
    showRecoveryCodesModal.value = true
    await loadProfile()
  } catch (err) {
    alert(err.message)
  }
}

async function handleDisableOwn2fa() {
  const pwd = prompt(t('settings_enter_pwd_disable_2fa') || 'Enter your account password to disable 2FA:')
  if (!pwd) return
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/2fa/disable', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ password: pwd }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to disable 2FA')
    loadProfile()
    loadUsers()
    flashType.value = 'success'
    flashMsg.value = '2FA has been disabled successfully.'
  } catch (err) {
    alert(err.message)
  }
}

async function toggleUserStatus(u) {
  const targetState = u.is_active ? 0 : 1
  const actionText = targetState ? 'activate' : 'lock'
  if (!confirm(`Are you sure you want to ${actionText} user '${u.username}'?`)) return
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${u.id}/status`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ is_active: targetState }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to update user status')
    flashType.value = 'success'
    flashMsg.value = `Status for '${u.username}' updated successfully.`
    loadUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}

async function deleteUser(u) {
  if (!confirm(`Permanently delete user account '${u.username}'? All active sessions will be terminated.`)) return
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${u.id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to delete user')
    flashType.value = 'success'
    flashMsg.value = `User '${u.username}' has been deleted.`
    loadUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}

function onUserCreated(createdUser) {
  flashType.value = 'success'
  flashMsg.value = `User '${createdUser.username}' created successfully.`
  loadUsers()
}

async function onProfileUpdated(updatedUser) {
  flashType.value = 'success'
  flashMsg.value = 'Account credentials updated successfully.'
  await loadProfile()
  await loadUsers()
}

async function onUserUpdated(updatedUser) {
  flashType.value = 'success'
  flashMsg.value = 'User permissions and configuration updated successfully.'
  await loadUsers()
  if (profile.value && updatedUser && updatedUser.id === profile.value.id) {
    await loadProfile()
  }
}

function onPasswordReset() {
  showResetModal.value = false
  flashType.value = 'success'
  flashMsg.value = 'User password reset successfully.'
}

function formatTime(iso) {
  if (!iso) return 'Never'
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    return d.toLocaleString('en-US', {
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
