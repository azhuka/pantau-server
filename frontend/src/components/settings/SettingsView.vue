<template>
  <div class="space-y-6">
    <!-- Header & Sub-Tab Navigation -->
    <div class="border-b border-gray-800 pb-4 flex items-center justify-between flex-wrap gap-4">
      <div>
        <h2 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// {{ activeTab === 'rbac' ? 'SYSTEM SETTINGS & AUTHORITY CONTROL (RBAC)' : 'MASTER CONTROL & THRESHOLDS' }}</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-1">
          {{ activeTab === 'rbac' ? 'Manajemen kredensial operator, autentikasi 2FA, dan matriks hak akses 3-tier.' : 'Pusat kendali internal, ambang batas insiden fisik, dan optimasi database MySQL.' }}
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
          <span>Otoritas & Pengguna</span>
        </button>
        <button
          @click="activeTab = 'master_control'"
          class="px-3 py-1.5 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
          :class="activeTab === 'master_control' ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow-sm' : 'text-gray-400 hover:text-gray-200'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          <span>Master Control & Ambang Batas</span>
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
      <!-- Operator Identity & 2FA Cards Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Panel 1: Profile & Password Change -->
        <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between flex-wrap gap-3 pb-3 border-b border-gray-800/80">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-cyan-950 border border-cyan-700/50 flex items-center justify-center text-cyan-400">
                  <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-bold text-gray-100 font-mono">{{ profile?.username || 'Operator' }}</span>
                    <span
                      class="text-[10px] font-bold font-mono px-2 py-0.5 rounded uppercase"
                      :class="profile?.is_master_admin ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-gray-800 text-gray-300 border border-gray-700'"
                    >
                      {{ profile?.is_master_admin ? 'Master Admin' : profile?.role }}
                    </span>
                  </div>
                  <div class="text-[11px] text-gray-400 font-mono mt-0.5">
                    Login Terakhir: {{ formatTime(profile?.last_login_at) }}
                  </div>
                </div>
              </div>

              <button
                @click="showChangePwd = !showChangePwd"
                class="px-2.5 py-1 rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-xs font-mono text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1.5"
              >
                <span>Ubah Password</span>
                <span class="text-[10px]">{{ showChangePwd ? '▲' : '▼' }}</span>
              </button>
            </div>

            <!-- Password Change Form -->
            <div v-if="showChangePwd" class="mt-4 pt-2">
              <form @submit.prevent="handleSelfPasswordChange" class="space-y-2.5 max-w-md">
                <div>
                  <label class="block text-[11px] font-mono text-gray-400 mb-0.5">Password Saat Ini</label>
                  <input
                    v-model="pwdForm.current_password"
                    type="password"
                    required
                    class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-2.5 py-1.5 font-mono focus:border-cyan-500 outline-none"
                  />
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div>
                    <label class="block text-[11px] font-mono text-gray-400 mb-0.5">Password Baru</label>
                    <input
                      v-model="pwdForm.new_password"
                      type="password"
                      required
                      minlength="8"
                      class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-2.5 py-1.5 font-mono focus:border-cyan-500 outline-none"
                    />
                  </div>
                  <div>
                    <label class="block text-[11px] font-mono text-gray-400 mb-0.5">Konfirmasi</label>
                    <input
                      v-model="pwdForm.confirm_password"
                      type="password"
                      required
                      minlength="8"
                      class="w-full bg-[#111827] border border-gray-800 text-gray-100 text-xs rounded px-2.5 py-1.5 font-mono focus:border-cyan-500 outline-none"
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  :disabled="pwdLoading"
                  class="px-3 py-1 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer"
                >
                  {{ pwdLoading ? t('saving', 'Saving...') : t('settings_change_pwd_btn') }}
                </button>
              </form>
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
                    Autentikasi Dua Langkah (2FA)
                  </h3>
                  <p class="text-[10px] text-gray-400">Standar RFC 6238 TOTP Authenticator</p>
                </div>
              </div>

              <span
                class="text-[10px] font-bold px-2 py-0.5 rounded"
                :class="profile?.totp_enabled ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'"
              >
                {{ profile?.totp_enabled ? '● 2FA Aktif' : '⚠ Nonaktif' }}
              </span>
            </div>

            <p class="text-xs text-gray-300 mt-3 leading-relaxed">
              {{ profile?.totp_enabled ? 'Akun Anda telah diamankan dengan autentikator dua langkah (Google Authenticator, Aegis, 2FAS, atau Authy).' : 'Lindungi akun Anda dari akses ilegal dengan mengaktifkan verifikasi dua langkah (2FA).' }}
            </p>
          </div>

          <div class="mt-4 pt-3 border-t border-gray-800/80 flex items-center justify-between">
            <span class="text-[11px] text-gray-400">
              {{ profile?.totp_enabled ? 'Perlindungan Kriptografis Aktif' : 'Belum Terpasang' }}
            </span>

            <div class="flex items-center gap-2">
              <button
                v-if="!profile?.totp_enabled"
                @click="showSetup2faModal = true"
                class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition cursor-pointer flex items-center gap-1.5"
              >
                <span>Aktifkan 2FA Sekarang</span>
              </button>
              <button
                v-else
                @click="handleDisableOwn2fa"
                class="px-3 py-1.5 rounded bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-bold transition cursor-pointer"
              >
                <span>Matikan 2FA</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Panel 3: User Accounts Directory (RBAC) -->
      <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative space-y-4">
        <!-- Directory Header -->
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest font-mono flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
              <span>// DIREKTORI PENGGUNA & HAK AKSES (RBAC)</span>
            </h3>
            <p class="text-xs text-gray-400 font-mono mt-0.5">
              Daftar akun terdaftar, pengaturan wewenang modular, dan cakupan server.
            </p>
          </div>

          <button
            @click="showAddModal = true"
            class="px-3 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold transition cursor-pointer flex items-center gap-1.5 shadow-sm"
          >
            <span>+</span>
            <span>Tambah Pengguna Baru</span>
          </button>
        </div>

        <!-- KPI Strip -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-gray-400 uppercase font-semibold">Total Pengguna</div>
            <div class="text-base font-extrabold text-gray-100 mt-0.5">{{ users.length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-cyan-400 uppercase font-semibold">Master Admin</div>
            <div class="text-base font-extrabold text-cyan-300 mt-0.5">{{ users.filter(u => u.role === 'master_admin').length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-emerald-400 uppercase font-semibold">Operator</div>
            <div class="text-base font-extrabold text-emerald-300 mt-0.5">{{ users.filter(u => u.role === 'operator').length }}</div>
          </div>
          <div class="p-2.5 rounded bg-[#0e1628] border border-gray-800 text-center">
            <div class="text-[10px] text-amber-400 uppercase font-semibold">Viewer (Tamu)</div>
            <div class="text-base font-extrabold text-amber-300 mt-0.5">{{ users.filter(u => u.role === 'viewer').length }}</div>
          </div>
        </div>

        <!-- Filter & Search Toolbar -->
        <div class="flex items-center justify-between flex-wrap gap-2.5 pt-2 border-t border-gray-800/80 font-mono text-xs">
          <div class="flex items-center gap-2 flex-wrap flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-gray-400 text-[11px]">Peran:</span>
              <select
                v-model="userRoleFilter"
                class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
              >
                <option value="">Semua Peran</option>
                <option value="master_admin">Master Admin</option>
                <option value="operator">Operator</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            <div class="flex items-center gap-1.5">
              <span class="text-gray-400 text-[11px]">Status:</span>
              <select
                v-model="userStatusFilter"
                class="bg-[#111827] border border-gray-800 rounded px-2.5 py-1 text-gray-200 text-xs focus:border-cyan-500 outline-none"
              >
                <option value="">Semua Status</option>
                <option value="active">Aktif</option>
                <option value="disabled">Terkunci</option>
              </select>
            </div>
          </div>

          <div class="w-full sm:w-64">
            <input
              v-model="userSearchQuery"
              type="search"
              placeholder="Cari pengguna (username)..."
              class="w-full bg-[#111827] border border-gray-800 rounded px-3 py-1 text-xs text-gray-200 focus:border-cyan-500 outline-none"
            />
          </div>
        </div>

        <!-- Users Table -->
        <div class="overflow-x-auto border border-gray-800/80 rounded-lg">
          <table class="w-full text-left font-mono border-collapse text-xs">
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
                    <span class="font-bold text-gray-100 font-mono text-xs">{{ u.username }}</span>
                    <span v-if="u.id === profile?.id" class="text-[10px] text-cyan-400 font-normal">(Anda)</span>
                  </div>
                  <div v-if="u.role === 'operator'" class="flex items-center gap-1.5 mt-1">
                    <span class="px-1.5 py-0.5 rounded text-[9px] bg-cyan-950 text-cyan-300 border border-cyan-800/80 font-bold">
                      {{ countPerms(u.permissions) }} Perms
                    </span>
                    <span
                      class="px-1.5 py-0.5 rounded text-[9px] font-bold"
                      :class="!u.allowed_server_ids || u.allowed_server_ids.length === 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-amber-950 text-amber-300 border border-amber-800'"
                    >
                      {{ !u.allowed_server_ids || u.allowed_server_ids.length === 0 ? 'Semua Server' : `${u.allowed_server_ids.length} Server` }}
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
                      <span>{{ u.is_active ? 'Aktif' : 'Terkunci' }}</span>
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
                  <!-- Unified Dropdown "Aksi ▾" Menu -->
                  <div class="relative inline-block text-left">
                    <button
                      type="button"
                      @click.stop="toggleActionDropdown(u.id)"
                      class="px-2.5 py-1 text-xs font-mono font-bold rounded bg-gray-900 hover:bg-cyan-950 border border-gray-700 hover:border-cyan-600/50 text-gray-200 hover:text-cyan-300 transition cursor-pointer flex items-center gap-1 shadow-sm"
                    >
                      <span>{{ t('settings_action_dropdown') }}</span>
                      <span class="text-[10px]">▾</span>
                    </button>

                    <!-- Dropdown Content -->
                    <div
                      v-if="openDropdownId === u.id"
                      @click.stop
                      class="absolute right-0 mt-1 w-44 rounded-lg bg-[#0b1326] border border-cyan-800/80 shadow-2xl z-50 py-1 font-mono text-xs divide-y divide-gray-800"
                    >
                      <div class="py-0.5">
                        <!-- Detail Pengguna -->
                        <button
                          type="button"
                          @click="openViewModal(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left text-gray-200 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
                        >
                          <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                          <span>Detail Pengguna</span>
                        </button>

                        <!-- Kelola 2FA (Admin Reset) -->
                        <button
                          v-if="profile?.is_master_admin && u.id !== profile?.id"
                          type="button"
                          @click="openAdmin2faModal(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left text-gray-200 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
                        >
                          <svg class="w-3.5 h-3.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                          <span>Kelola 2FA</span>
                        </button>
                      </div>

                      <div class="py-0.5">
                        <!-- Edit Pengguna -->
                        <button
                          v-if="canEditUser(u)"
                          type="button"
                          @click="openEditModal(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left text-gray-200 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
                        >
                          <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                          <span>Edit Pengguna</span>
                        </button>

                        <!-- Reset Password -->
                        <button
                          type="button"
                          @click="openResetModal(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left text-gray-200 hover:text-white hover:bg-cyan-950/80 flex items-center gap-2 cursor-pointer transition"
                        >
                          <svg class="w-3.5 h-3.5 text-yellow-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                          <span>Reset Password</span>
                        </button>
                      </div>

                      <div v-if="u.role !== 'master_admin' && u.id !== profile?.id" class="py-0.5">
                        <!-- Kunci / Buka Kunci -->
                        <button
                          type="button"
                          @click="toggleUserStatus(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left flex items-center gap-2 cursor-pointer transition"
                          :class="u.is_active ? 'text-amber-400 hover:bg-amber-950/60' : 'text-emerald-400 hover:bg-emerald-950/60'"
                        >
                          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                          <span>{{ u.is_active ? 'Kunci Akun' : 'Buka Kunci' }}</span>
                        </button>

                        <!-- Hapus Pengguna -->
                        <button
                          type="button"
                          @click="deleteUser(u); openDropdownId = null"
                          class="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/60 flex items-center gap-2 cursor-pointer transition"
                        >
                          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                          <span>Hapus Pengguna</span>
                        </button>
                      </div>
                    </div>
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

    <EditUserModal
      v-if="showEditModal && editingUser"
      :user="editingUser"
      :current-user-id="profile?.id"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showEditModal = false"
      @updated="onUserUpdated"
    />

    <ViewUserModal
      v-if="showViewModal && viewingUser"
      :user="viewingUser"
      :current-user-id="profile?.id"
      :permissions-meta="permissionsMeta"
      :servers-list="serversList"
      @close="showViewModal = false"
      @edit="openEditModal"
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import MasterControlSection from './MasterControlSection.vue'
import AddUserModal from './modals/AddUserModal.vue'
import EditUserModal from './modals/EditUserModal.vue'
import ViewUserModal from './modals/ViewUserModal.vue'
import Admin2faModal from './modals/Admin2faModal.vue'
import Setup2faModal from './modals/Setup2faModal.vue'
import ResetPasswordModal from './modals/ResetPasswordModal.vue'

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

const showChangePwd = ref(false)
const pwdLoading = ref(false)
const pwdForm = ref({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const showAddModal = ref(false)
const showEditModal = ref(false)
const editingUser = ref(null)

const showViewModal = ref(false)
const viewingUser = ref(null)

const showAdmin2faModal = ref(false)
const targetAdmin2faUser = ref(null)

const showSetup2faModal = ref(false)

const showResetModal = ref(false)
const targetResetUser = ref(null)

const flashMsg = ref('')
const flashType = ref('success')

function handleGlobalClick() {
  openDropdownId.value = null
}

onMounted(() => {
  window.addEventListener('click', handleGlobalClick)
  loadMetadata()
  loadProfile()
  loadUsers()
})

onUnmounted(() => {
  window.removeEventListener('click', handleGlobalClick)
})

function toggleActionDropdown(userId) {
  openDropdownId.value = openDropdownId.value === userId ? null : userId
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

function canEditUser(u) {
  if (u.role === 'master_admin' && u.id !== profile.value?.id) return false
  return true
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

function openViewModal(user) {
  viewingUser.value = user
  showViewModal.value = true
}

function openEditModal(user) {
  editingUser.value = user
  showEditModal.value = true
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
  flashMsg.value = 'Autentikasi dua langkah (2FA) berhasil diaktifkan untuk akun Anda.'
}

async function handleDisableOwn2fa() {
  const pwd = prompt('Masukkan kata sandi akun Anda untuk mematikan 2FA:')
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
    if (!res.ok) throw new Error(data.detail || 'Gagal mematikan 2FA')
    loadProfile()
    loadUsers()
    flashType.value = 'success'
    flashMsg.value = '2FA telah berhasil dimatikan.'
  } catch (err) {
    alert(err.message)
  }
}

async function handleSelfPasswordChange() {
  if (pwdForm.value.new_password !== pwdForm.value.confirm_password) {
    flashType.value = 'error'
    flashMsg.value = 'Password baru dan konfirmasi tidak cocok.'
    return
  }
  pwdLoading.value = true
  flashMsg.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/users/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        current_password: pwdForm.value.current_password,
        new_password: pwdForm.value.new_password,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Gagal mengubah password')
    flashType.value = 'success'
    flashMsg.value = 'Password Anda berhasil diperbarui.'
    showChangePwd.value = false
    pwdForm.value = { current_password: '', new_password: '', confirm_password: '' }
    loadProfile()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  } finally {
    pwdLoading.value = false
  }
}

async function toggleUserStatus(u) {
  const targetState = u.is_active ? 0 : 1
  const actionText = targetState ? 'aktifkan' : 'kunci'
  if (!confirm(`Yakin ingin ${actionText} akun pengguna '${u.username}'?`)) return
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
    if (!res.ok) throw new Error(data.detail || 'Gagal mengubah status akun')
    flashType.value = 'success'
    flashMsg.value = `Status akun '${u.username}' berhasil diperbarui.`
    loadUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}

async function deleteUser(u) {
  if (!confirm(`Hapus akun pengguna '${u.username}' secara permanen? Seluruh sesi aktif akan dicabut.`)) return
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/users/${u.id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Gagal menghapus pengguna')
    flashType.value = 'success'
    flashMsg.value = `Pengguna '${u.username}' telah dihapus.`
    loadUsers()
  } catch (err) {
    flashType.value = 'error'
    flashMsg.value = err.message
  }
}

function onUserCreated() {
  showAddModal.value = false
  flashType.value = 'success'
  flashMsg.value = 'Pengguna baru berhasil didaftarkan.'
  loadUsers()
}

function onUserUpdated() {
  showEditModal.value = false
  flashType.value = 'success'
  flashMsg.value = 'Data wewenang dan akun pengguna berhasil diperbarui.'
  loadUsers()
}

function onPasswordReset() {
  showResetModal.value = false
  flashType.value = 'success'
  flashMsg.value = 'Password pengguna berhasil direset.'
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
