<template>
  <!-- Floating Workspace Modal Backdrop -->
  <div
    v-if="isOpen"
    v-show="!isMinimized"
    class="fixed inset-0 z-50 bg-black/75 backdrop-blur-[4px] flex items-center justify-center p-2 sm:p-4 transition-all duration-200"
  >
    <!-- Modal Window Card (Tactical Cyber Command Deck) -->
    <div
      id="server-workspace-modal"
      :class="[
        'hud-tactical-card shadow-2xl flex flex-col transition-all duration-200 overflow-hidden relative',
        isMaximized
          ? 'fixed inset-0 w-screen h-screen rounded-none z-50'
          : 'w-[92vw] max-w-[1600px] h-[90vh] min-h-[620px] rounded-xl'
      ]"
    >
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- 1. WINDOW TITLEBAR (Fixed Height, Single Line, Pinned Window Controls) -->
      <div
        class="bg-[#060a15] border-b border-cyan-500/20 px-4 py-2 flex items-center justify-between select-none cursor-default shrink-0 gap-3"
        @dblclick="toggleMaximize"
      >
        <!-- Left: Host Info & Status -->
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-7 h-7 rounded bg-cyan-950/80 border border-cyan-400/50 flex items-center justify-center text-cyan-300 font-bold text-sm shadow-[0_0_10px_rgba(56,189,248,0.25)] shrink-0">
            <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
              <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
              <line x1="6" y1="6" x2="6.01" y2="6"/>
              <line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2 font-mono flex-wrap sm:flex-nowrap">
              <span class="text-xs text-cyan-400 font-bold">Server Details:</span>
              <span class="font-extrabold text-gray-100 text-sm tracking-tight truncate">
                {{ server?.hostname || t('ws_loading_host') }}
              </span>
              <span
                v-if="server?.is_maintenance"
                class="inline-flex items-center gap-1.5 px-2 py-0.2 rounded text-[11px] font-bold bg-amber-950/80 text-amber-300 border border-amber-600/60 shrink-0 cursor-pointer hover:border-amber-400 transition"
                @click="openMaintenanceModal"
                :title="t('tooltip_view_maint')"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                <span>{{ t('status_maint') }}</span>
                <span class="text-[10px] text-amber-200 underline font-semibold">{{ t('btn_view') || 'View' }}</span>
              </span>
              <span
                v-else-if="isServerOnline(server)"
                class="inline-flex items-center gap-1 px-2 py-0.2 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 shrink-0"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
                LIVE
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1 px-2 py-0.2 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-700/60 shrink-0"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-rose-500 radar-critical"></span>
                DOWN
              </span>
              <span class="text-xs font-mono text-cyan-300 font-semibold shrink-0">
                ({{ server?.ip_address }})
              </span>
              <span
                v-if="server?.is_proxmox_ha"
                class="text-[10px] px-1.5 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold shrink-0"
                title="Host is protected by Proxmox HA"
              >
                PROXMOX HA
              </span>
            </div>
            <div class="text-[11px] text-gray-400 font-mono flex items-center gap-1.5 mt-0.5">
              <span>{{ server?.os_label || 'Linux' }}</span>
              <span class="text-gray-600">·</span>
              <span>Kernel {{ server?.kernel || '-' }}</span>
              <span class="text-gray-600">·</span>
              <span>Agent v{{ server?.agent_version || '-' }}</span>
              <button
                @click="refreshData"
                :disabled="loading"
                class="ml-1 text-gray-400 hover:text-cyan-300 transition cursor-pointer disabled:opacity-50"
                :title="t('syncing')"
              >
                <svg
                  class="w-3.5 h-3.5 inline"
                  :class="{ 'animate-spin text-cyan-400': loading }"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                  <path d="M3 3v5h5" />
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
                  <path d="M16 21h5v-5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Center-Right: ASSET QUICK-SWITCHER & PINNED WINDOW CONTROLS -->
        <div class="flex items-center gap-2 font-mono shrink-0 ml-auto" @click.stop>
          <!-- Asset Switcher -->
          <div class="flex items-center bg-[#050811] border border-cyan-900/50 rounded p-0.5">
            <button
              @click="navigateHost(-1)"
              class="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer flex items-center justify-center"
              title="Previous Server (Hotkeys [ )"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
            </button>

            <!-- Searchable Switcher Dropdown Trigger -->
            <div class="relative">
              <button
                @click="showHostDropdown = !showHostDropdown"
                class="px-2.5 py-1 text-xs font-mono text-gray-200 hover:text-cyan-300 flex items-center gap-1.5 transition cursor-pointer font-semibold"
                :title="t('ws_search_asset')"
              >
                <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                <span class="max-w-[130px] truncate">{{ server?.hostname }}</span>
                <span class="text-[10px] text-cyan-400">▾</span>
              </button>

              <!-- Popover Dropdown -->
              <div
                v-if="showHostDropdown"
                class="absolute right-0 top-full mt-2 w-80 bg-[#080d19] border border-cyan-500/50 rounded-xl shadow-[0_12px_36px_rgba(0,0,0,0.8)] p-2.5 z-[9999] text-xs backdrop-blur-md"
              >
                <div class="relative mb-2">
                  <input
                    v-model="hostSearchQuery"
                    type="text"
                    :placeholder="t('ws_search_asset')"
                    class="w-full bg-[#04060c] border border-cyan-800/80 rounded px-2.5 py-1.5 text-xs text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-400 font-mono"
                    autofocus
                  />
                </div>
                <div class="max-h-60 overflow-y-auto space-y-1 divide-y divide-gray-800/40">
                  <div
                    v-for="h in filteredHosts"
                    :key="h.id"
                    @click="selectHost(h.id)"
                    class="p-2 rounded hover:bg-cyan-950/40 cursor-pointer flex items-center justify-between transition"
                    :class="{ 'bg-cyan-950/70 font-bold border border-cyan-500/40': h.id === currentServerId }"
                  >
                    <div>
                      <div class="font-mono text-gray-200 flex items-center gap-1.5 text-xs font-semibold">
                        <span
                          class="w-2 h-2 rounded-full"
                          :class="h.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500 radar-critical'"
                        ></span>
                        <span>{{ h.hostname }}</span>
                      </div>
                      <div class="text-[11px] text-gray-400 font-mono">{{ h.ip_address }}</div>
                    </div>
                    <span class="text-[10px] text-gray-400 font-mono uppercase bg-gray-900/60 px-1.5 py-0.5 rounded">{{ h.group_name }}</span>
                  </div>
                </div>
              </div>
            </div>

            <button
              @click="navigateHost(1)"
              class="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer flex items-center justify-center"
              title="Next Server (Hotkeys ] )"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>

          <!-- Pinned Window Controls (Far Right Corner) -->
          <div class="flex items-center gap-1 border-l border-cyan-500/30 pl-2">
            <button
              @click="$emit('minimize')"
              class="p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800/80 transition cursor-pointer"
              :title="t('ws_minimize')"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button
              @click="toggleMaximize"
              class="p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800/80 transition cursor-pointer font-bold text-xs"
              :title="isMaximized ? t('ws_restore') : t('ws_maximize')"
            >
              <svg v-if="!isMaximized" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="18" height="18" x="3" y="3" rx="2"/>
                <line x1="3" y1="9" x2="21" y2="9"/>
              </svg>
              <svg v-else class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="13" height="13" x="8" y="3" rx="1.5"/>
                <path d="M4 8H3a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-1"/>
              </svg>
            </button>
            <button
              @click="handleClose"
              class="p-1.5 rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/60 transition cursor-pointer"
              :title="t('ws_close')"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 2. COMMAND ACTION DECK (Dedicated Hero Toolbar) -->
      <div class="bg-[#080d1a] border-b border-cyan-500/20 px-4 py-2 flex items-center justify-between select-none shrink-0 font-mono flex-wrap gap-2">
        <!-- Grup 1: Konsol Khusus (Terminal & File Manager) & Mode Pemeliharaan -->
        <div class="flex items-center gap-2">
          <div class="flex items-center bg-[#050811] border border-cyan-900/60 rounded p-0.5">
            <button
              v-if="userPerms.can_terminal"
              @click="openTerminalModal"
              class="px-2.5 py-1 text-xs text-gray-200 hover:text-cyan-300 hover:bg-cyan-950/60 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :class="isTerminalOpen ? 'bg-cyan-950/90 text-cyan-300 border border-cyan-500/70 shadow-[0_0_10px_rgba(56,189,248,0.25)]' : ''"
              :title="t('tooltip_terminal_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="4 17 10 11 4 5"/>
                <line x1="12" y1="19" x2="20" y2="19"/>
              </svg>
              <span>{{ t('toolbar_terminal') }}</span>
            </button>
            <span v-if="userPerms.can_terminal && userPerms.can_file_manager" class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              v-if="userPerms.can_file_manager"
              @click="openFileManagerModal"
              class="px-2.5 py-1 text-xs text-gray-200 hover:text-cyan-300 hover:bg-cyan-950/60 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_fm_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              </svg>
              <span>{{ t('toolbar_fm') }}</span>
            </button>
            <span v-if="(userPerms.can_terminal || userPerms.can_file_manager) && (userPerms.can_manage_servers || userPerms.can_server_control)" class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              v-if="userPerms.can_manage_servers || userPerms.can_server_control"
              @click="openMaintenanceModal"
              class="px-2.5 py-1 text-xs rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :class="server?.is_maintenance ? 'bg-amber-950/90 text-amber-300 border border-amber-500/80 shadow-[0_0_12px_rgba(245,158,11,0.25)]' : 'text-gray-300 hover:text-amber-300 hover:bg-amber-950/40'"
              :title="t('tooltip_maint_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              <span>{{ t('toolbar_maint') }}</span>
              <span v-if="server?.is_maintenance" class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
            </button>
          </div>
        </div>

        <!-- Grup 2: Siklus & Kontrol Daya Sistem -->
        <div v-if="userPerms.can_apt || userPerms.can_server_control" class="flex items-center gap-2">
          <div class="flex items-center bg-[#050811] border border-cyan-900/60 rounded p-0.5">
            <button
              v-if="userPerms.can_apt"
              @click="triggerOSUpdate"
              :disabled="!isServerOnline(server) || aptTaskRunning"
              class="px-2.5 py-1 text-xs rounded transition flex items-center gap-1.5 font-bold"
              :class="(!isServerOnline(server) || aptTaskRunning) ? 'text-gray-500 opacity-40 cursor-not-allowed' : 'text-emerald-400 hover:bg-emerald-950/60 cursor-pointer'"
              :title="!isServerOnline(server) ? 'Asset is offline' : (aptTaskRunning ? 'An OS package operation is currently running' : t('tooltip_update_btn'))"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                <path d="M3 3v5h5"/>
                <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                <path d="M16 21h5v-5"/>
              </svg>
              <span>{{ t('toolbar_update_os') }}</span>
            </button>
            <span v-if="userPerms.can_apt" class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              v-if="userPerms.can_apt"
              @click="triggerOSUpgrade"
              :disabled="!isServerOnline(server) || aptTaskRunning || (server?.apt_upgradable || 0) <= 0"
              class="px-2.5 py-1 text-xs rounded transition flex items-center gap-1.5 font-bold"
              :class="(!isServerOnline(server) || aptTaskRunning || (server?.apt_upgradable || 0) <= 0) ? 'text-gray-500 opacity-40 cursor-not-allowed' : 'text-amber-300 bg-amber-950/70 border border-amber-700/60 hover:bg-amber-900/70 cursor-pointer'"
              :title="!isServerOnline(server) ? 'Asset is offline' : (aptTaskRunning ? 'An OS package operation is currently running' : ((server?.apt_upgradable || 0) <= 0 ? 'All OS packages are up-to-date' : t('tooltip_upgrade_btn')))"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span>{{ t('toolbar_upgrade_os') }}</span>
              <span v-if="(server?.apt_upgradable || 0) > 0" class="px-1.5 py-0.2 rounded bg-amber-500 text-black text-[10px] font-black">
                {{ server?.apt_upgradable }}
              </span>
            </button>
            <span v-if="userPerms.can_apt && userPerms.can_server_control" class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              v-if="userPerms.can_server_control"
              @click="openGuardrailConfirm('reboot')"
              :disabled="!isServerOnline(server)"
              class="px-2.5 py-1 text-xs rounded transition flex items-center gap-1.5 font-bold"
              :class="!isServerOnline(server) ? 'text-gray-500 opacity-40 cursor-not-allowed' : 'text-amber-400 hover:bg-amber-950/60 cursor-pointer'"
              :title="!isServerOnline(server) ? 'Asset is offline' : t('tooltip_reboot_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                <path d="M3 3v5h5"/>
              </svg>
              <span>{{ t('toolbar_reboot') }}</span>
            </button>
            <span v-if="userPerms.can_server_control" class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <!-- POWER OFF (Proteksi Proxmox HA) -->
            <button
              v-if="userPerms.can_server_control && server?.is_proxmox_ha"
              disabled
              class="px-2.5 py-1 text-xs text-gray-500 bg-gray-900/50 rounded cursor-not-allowed opacity-40 border border-dashed border-rose-900 flex items-center gap-1.5 font-bold"
              :title="t('tooltip_poweroff_ha_blocked')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
                <line x1="12" y1="2" x2="12" y2="12"/>
              </svg>
              <span>{{ t('toolbar_poweroff') }}</span>
            </button>
            <button
              v-else-if="userPerms.can_server_control"
              @click="openGuardrailConfirm('poweroff')"
              :disabled="!isServerOnline(server)"
              class="px-2.5 py-1 text-xs rounded transition flex items-center gap-1.5 font-bold"
              :class="!isServerOnline(server) ? 'text-gray-500 opacity-40 cursor-not-allowed' : 'text-rose-400 hover:bg-rose-950/60 cursor-pointer'"
              :title="!isServerOnline(server) ? 'Asset is offline' : t('tooltip_poweroff_btn')"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>
                <line x1="12" y1="2" x2="12" y2="12"/>
              </svg>
              <span>{{ t('toolbar_poweroff') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 2.5 INTEGRATED WEB TERMINAL PANEL (Terintegrasi, Persis Seperti Blueprint Asli) -->
      <div v-if="isTerminalOpen && server" class="px-4 bg-[#080d1a] border-b border-cyan-500/20">
        <ServerWorkspaceTerminal
          ref="workspaceTerminalRef"
          :server="server"
          :lease-seconds="terminalLeaseSeconds"
          @request-close="showTerminalCloseModal = true"
          @request-lock="showTerminalLockModal = true"
        />
      </div>

      <!-- Active Background OS Package Task Banner -->
      <div
        v-if="aptTaskRunning && !aptRunnerOpen"
        class="bg-cyan-950/70 border-b border-cyan-500/50 px-4 py-2 flex items-center justify-between gap-3 text-xs font-mono shrink-0"
      >
        <div class="flex items-center gap-2 text-cyan-200 min-w-0">
          <svg class="w-3.5 h-3.5 text-cyan-400 animate-spin shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
          </svg>
          <span class="truncate">{{ aptTaskLabel }} is running in the background...</span>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="px-2 py-0.5 rounded bg-gray-900/90 border border-cyan-800/60 text-cyan-300 text-[11px] tabular-nums">
            {{ aptElapsedFormatted }}
          </span>
          <button
            type="button"
            @click="aptRunnerOpen = true"
            class="px-2.5 py-1 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold text-[11px] cursor-pointer transition"
          >
            View Output
          </button>
        </div>
      </div>

      <!-- 3. SUB-TABS NAVIGATION BAR (Tab Taktis Ramping) -->
      <div class="bg-[#070b16] border-b border-cyan-500/20 px-4 flex items-center gap-1 overflow-x-auto shrink-0 select-none py-1.5 font-mono text-xs">
        <button
          v-for="tab in subTabs"
          :key="tab.id"
          @click="activeSubTab = tab.id"
          class="px-2.5 py-1.5 rounded text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 whitespace-nowrap border"
          :class="[
            activeSubTab === tab.id
              ? 'bg-cyan-950/80 text-cyan-300 border-cyan-500/60 shadow-[0_0_8px_rgba(56,189,248,0.2)] font-bold'
              : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/40 border-transparent'
          ]"
        >
          <!-- Tab Icon SVG -->
          <svg v-if="tab.id === 'overview'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          <svg v-else-if="tab.id === 'problems'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <svg v-else-if="tab.id === 'services'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <svg v-else-if="tab.id === 'ports'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
          <svg v-else-if="tab.id === 'processes'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/></svg>
          <svg v-else-if="tab.id === 'firewall'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <svg v-else-if="tab.id === 'accounts'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          <svg v-else-if="tab.id === 'cron'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <svg v-else-if="tab.id === 'fim'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <svg v-else-if="tab.id === 'packages'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16.5 9.4-9-5.19M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
          <svg v-else-if="tab.id === 'ssl'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <svg v-else-if="tab.id === 'logs'" class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>{{ tab.label }}</span>
          <!-- Dynamic Badges -->
          <span
            v-if="tab.id === 'problems' && activeNonIgnoredProblemsCount > 0"
            class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-500 text-white ml-0.5"
          >
            {{ activeNonIgnoredProblemsCount }}
          </span>
          <span
            v-else-if="tab.id === 'accounts' && activeSSHSessions.length > 0"
            class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-400 text-black radar-warning ml-0.5"
            :title="t('human_intercept_badge')"
          >
            {{ activeSSHSessions.length }}
          </span>
          <span
            v-else-if="tab.badge"
            class="text-[10px] opacity-80 font-mono ml-0.5"
          >
            ({{ tab.badge }})
          </span>
        </button>
      </div>

      <!-- 3. MODAL CONTENT BODY -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        <!-- Loading State -->
        <div v-if="loading && !server" class="py-24 text-center text-gray-400 text-xs font-mono">
          <div class="mb-3 flex justify-center">
            <svg class="w-8 h-8 animate-spin text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
              <path d="M16 21h5v-5"/>
            </svg>
          </div>
          <div>{{ t('ws_loading_telemetry') }}</div>
        </div>

        <template v-else-if="server">
          <WorkspaceOverviewTab
            v-if="activeSubTab === 'overview'"
            :server="server"
            :processes-count="processesList.length"
            :can-edit-notes="Boolean(currentUser?.is_master_admin || userPerms.can_manage_servers || userPerms.can_server_control)"
            @note-updated="loadServerData()"
          />
          <WorkspaceProblemsTab
            v-else-if="activeSubTab === 'problems'"
            :server-id="currentServerId"
            :problems="serverProblems"
            :current-user="currentUser"
            @terminate-ssh-problem="terminateSSHSessionFromProblem"
            @ack-problem="handleWorkspaceProblemAck"
            @switch-tab="activeSubTab = $event"
            @refresh="loadServerData(); emit('refresh-problems')"
          />
          <WorkspaceServicesTab
            v-else-if="activeSubTab === 'services'"
            :server-id="currentServerId"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            :can-manage="Boolean(currentUser?.is_master_admin || currentUser?.role === 'operator_utama' || userPerms.can_services)"
            :services="servicesList"
            :monitored-services="monitoredServicesList"
            :available-logs="availableLogsList"
            @service-action="handleServiceAction"
            @refresh="loadServerData()"
            @monitored-updated="handleMonitoredUpdated"
            @open-logs-tab="src => { initialLogSource = src; activeSubTab = 'logs' }"
          />
          <WorkspacePortsTab
            v-else-if="activeSubTab === 'ports'"
            :ports="portsList"
            :monitored-services="monitoredServicesList"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            :can-services="Boolean(currentUser?.is_master_admin || currentUser?.role === 'operator_utama' || userPerms.can_services)"
            :can-processes="Boolean(currentUser?.is_master_admin || currentUser?.role === 'operator_utama' || userPerms.can_processes)"
            :can-firewall="Boolean(currentUser?.is_master_admin || currentUser?.role === 'operator_utama' || userPerms.can_firewall)"
            @monitor-port="handleMonitorPort"
            @kill-process="killProcess"
            @firewall-port="handleFirewallPort"
          />
          <WorkspaceProcessesTab
            v-else-if="activeSubTab === 'processes'"
            :processes="processesList"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            @kill-process="killProcess"
            @refresh="loadServerData()"
          />
          <WorkspaceFirewallTab
            v-else-if="activeSubTab === 'firewall'"
            :firewall-data="firewallData"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            :busy="actionBusy"
            @firewall-action="handleGenericAction"
          />
          <WorkspaceAccountsTab
            v-else-if="activeSubTab === 'accounts'"
            :server-id="currentServerId"
            :active-s-s-h-sessions="activeSSHSessions"
            :accounts-list="accountsList"
            :groups-list="groupsList"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            @terminate-ssh="terminateSSHSession"
            @user-action="handleUserAction"
          />
          <WorkspaceCronTab
            v-else-if="activeSubTab === 'cron'"
            :cron-data="cronData"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            @cron-action="handleGenericAction"
          />
          <WorkspaceFimTab
            v-else-if="activeSubTab === 'fim'"
            :fim-paths="fimPathsList"
            :fim-events="fimEventsList"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            @fim-action="handleGenericAction"
            @fim-ack="handleFimAck"
            @fim-unack="handleFimUnack"
            @fim-ack-all="handleFimAckAll"
          />
          <WorkspacePackagesTab
            v-else-if="activeSubTab === 'packages'"
            :server="server"
            :packages-list="packagesList"
            :can-apt="userPerms.can_apt"
            :is-online="isServerOnline(server)"
            @upgrade-package="triggerPackageUpgrade"
          />
          <WorkspaceSslTab
            v-else-if="activeSubTab === 'ssl'"
            :ssl-certs-list="sslCertsList"
            :is-online="Boolean(server?.is_online)"
            :is-viewer="currentUser?.role === 'viewer'"
            @ssl-action="handleGenericAction"
          />
          <WorkspaceLogsTab
            v-else-if="activeSubTab === 'logs'"
            :server-id="currentServerId"
            :server-online="Boolean(server?.is_online)"
            :logs-list="logsList"
            :available-logs="availableLogsList"
            :initial-source="initialLogSource"
          />
        </template>
      </div>

      <!-- 4. MODAL FOOTER BAR -->
      <div class="bg-[#080d19] border-t border-cyan-500/20 px-4 py-2 flex items-center justify-between text-xs text-gray-400 font-mono shrink-0 select-none">
        <div>
          <span>HOST_ID: #{{ server?.id }}</span>
          <span class="mx-2 text-gray-600">·</span>
          <span>HOTKEYS: <kbd class="px-1.5 py-0.2 bg-gray-900 border border-gray-700 rounded text-cyan-300 font-bold">[</kbd> PREV / <kbd class="px-1.5 py-0.2 bg-gray-900 border border-gray-700 rounded text-cyan-300 font-bold">]</kbd> NEXT / <kbd class="px-1.5 py-0.2 bg-gray-900 border border-gray-700 rounded text-cyan-300 font-bold">ESC</kbd> {{ t('shelf_close') }}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
          <span class="text-emerald-400 font-bold">SECURE CONNECTION ACTIVE</span>
        </div>
      </div>
    </div>

    <!-- GUARDRAIL CONFIRMATION MODAL (Reboot & Power Off) -->
    <div
      v-if="showGuardrailModal"
      class="fixed inset-0 z-60 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
    >
      <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-rose-500/50">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <div class="flex items-center justify-between border-b border-rose-500/30 pb-2">
          <div class="flex items-center gap-2 text-rose-400 font-bold text-xs uppercase">
            <svg class="w-4 h-4 text-rose-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span>GUARDRAIL: POWER CONTROL CONFIRMATION</span>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700">
            {{ guardrailAction === 'reboot' ? 'SERVICE DISRUPTION' : 'CRITICAL IMPACT' }}
          </span>
        </div>

        <form @submit.prevent="executeGuardrailAction" class="space-y-3">
          <div class="text-xs text-gray-200 space-y-2">
            <div class="text-gray-400">Target Host:</div>
            <div class="text-cyan-300 font-bold text-sm bg-cyan-950/40 p-2 rounded border border-cyan-800/40">
              {{ server?.hostname }} ({{ server?.ip_address }})
            </div>
            <div class="text-gray-300 leading-relaxed pt-1">
              {{ guardrailAction === 'reboot'
                ? 'Restart host operating system. All running services and active network connections will be interrupted temporarily until reboot completes.'
                : 'Power off server (Shutdown). Host cannot be powered back on remotely via this dashboard (requires IPMI or hypervisor console access).'
              }}
            </div>
          </div>

          <div v-if="guardrailError" class="p-2 rounded bg-rose-950/60 border border-rose-500/50 text-rose-300 text-[11px]">
            {{ guardrailError }}
          </div>

          <div>
            <label class="block text-[11px] text-gray-300 font-bold mb-1">Operator Password</label>
            <input
              v-model="guardrailPassword"
              type="password"
              required
              autocomplete="current-password"
              placeholder="Enter your password to authorize"
              class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-xs text-gray-100 focus:outline-none focus:border-cyan-400"
            />
          </div>

          <div v-if="currentUser?.totp_enabled || userHasTotp">
            <label class="block text-[11px] text-gray-300 font-bold mb-1">2FA / TOTP Code</label>
            <input
              v-model="guardrailTotp"
              type="text"
              maxlength="6"
              inputmode="numeric"
              pattern="[0-9]*"
              placeholder="6-digit code"
              class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-xs text-gray-100 tracking-widest focus:outline-none focus:border-cyan-400"
            />
          </div>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-gray-800">
            <button
              type="button"
              @click="showGuardrailModal = false"
              class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:text-white text-xs font-bold transition cursor-pointer"
            >
              CANCEL
            </button>
            <button
              type="submit"
              :disabled="guardrailSubmitting || !guardrailPassword"
              class="px-4 py-1.5 rounded text-white text-xs font-bold transition cursor-pointer shadow-lg disabled:opacity-40 disabled:cursor-not-allowed"
              :class="guardrailAction === 'reboot' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-rose-600 hover:bg-rose-500'"
            >
              {{ guardrailSubmitting ? 'EXECUTING...' : (guardrailAction === 'reboot' ? 'EXECUTE REBOOT' : 'EXECUTE POWER OFF') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- DEDICATED FLOATING REMOTE FILE MANAGER MODAL -->
    <RemoteFileManagerModal
      :open="showFileManagerModal"
      :server="server || { id: currentServerId, hostname: server?.hostname || 'Server', ip_address: server?.ip_address }"
      @close="showFileManagerModal = false"
      @open-terminal="handleTerminalFromFm"
    />

    <!-- MODAL MODE PEMELIHARAAN (Tactical Maintenance Mode Window) -->
    <div
      v-if="showMaintenanceModal"
      class="fixed inset-0 z-[15000] flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 font-mono select-none"
      @keydown.esc="closeMaintenanceModal"
    >
      <div class="bg-[#080d19] border border-cyan-500/50 shadow-[0_20px_50px_rgba(0,0,0,0.9)] rounded-xl w-full max-w-[500px] overflow-hidden">
        <!-- Titlebar -->
        <div class="bg-[#060a14] border-b border-cyan-500/30 px-4 py-3 flex items-center justify-between">
          <div class="flex items-center gap-2 text-amber-400 font-bold text-xs uppercase">
            <svg class="w-4 h-4 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
            <span>{{ t('maint_modal_title') }}</span>
          </div>
          <button
            type="button"
            @click="closeMaintenanceModal"
            class="text-gray-400 hover:text-white transition cursor-pointer p-1"
            title="Close (Esc)"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <!-- Body -->
        <div class="p-4 space-y-4 text-xs">
          <p class="text-gray-400 leading-relaxed">
            {{ t('maint_modal_desc') }}
          </p>

          <!-- Current Status Card -->
          <div class="p-3 rounded-lg bg-[#040711] border border-cyan-900/60 space-y-1.5">
            <div class="flex items-center justify-between">
              <span class="text-gray-400">{{ t('maint_status_label') }}</span>
              <span
                v-if="server?.is_maintenance"
                class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-bold bg-amber-950/80 text-amber-300 border border-amber-600/60"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                {{ t('maint_active') }}
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                {{ t('maint_inactive') }}
              </span>
            </div>

            <div v-if="server?.maintenance_reason" class="text-[11px] text-gray-300 flex items-center justify-between">
              <span class="text-gray-500">{{ t('maint_reason_label') }}</span>
              <span class="text-cyan-200 font-medium truncate max-w-[280px]" :title="server.maintenance_reason">{{ server.maintenance_reason }}</span>
            </div>

            <div v-if="server?.maintenance_until" class="text-[11px] text-gray-300 flex items-center justify-between">
              <span class="text-gray-500">{{ t('maint_until_label') }}</span>
              <span class="text-amber-200 font-bold">{{ formatMaintenanceDate(server.maintenance_until) }}</span>
            </div>
          </div>

          <!-- Duration Picker -->
          <div>
            <label class="block text-gray-300 font-bold mb-1.5">{{ t('maint_duration_label') }}</label>
            <select
              v-model="maintDurationMinutes"
              class="w-full bg-[#03060f] border border-cyan-900 focus:border-cyan-400 rounded px-3 py-2 text-gray-200 text-xs focus:outline-none transition cursor-pointer"
            >
              <option :value="30">{{ t('maint_dur_30m') }}</option>
              <option :value="60">{{ t('maint_dur_1h') }}</option>
              <option :value="240">{{ t('maint_dur_4h') }}</option>
              <option :value="1440">{{ t('maint_dur_24h') }}</option>
              <option :value="0">{{ t('maint_dur_manual') }}</option>
            </select>
          </div>

          <!-- Reason Input -->
          <div>
            <label class="block text-gray-300 font-bold mb-1.5">{{ t('maint_reason_input_label') }}</label>
            <input
              v-model="maintReasonInput"
              type="text"
              :placeholder="t('maint_reason_placeholder')"
              class="w-full bg-[#03060f] border border-cyan-900 focus:border-cyan-400 rounded px-3 py-2 text-gray-100 text-xs focus:outline-none transition"
            />
          </div>
        </div>

        <!-- Footer Buttons -->
        <div class="bg-[#060a14] border-t border-cyan-500/20 px-4 py-3 flex items-center justify-between gap-2">
          <div>
            <button
              v-if="server?.is_maintenance"
              type="button"
              @click="submitMaintenance('disable')"
              :disabled="maintSubmitting"
              class="px-3 py-1.5 rounded bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800 transition cursor-pointer font-bold flex items-center gap-1.5 shadow"
            >
              <svg v-if="maintSubmitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              <span>{{ t('maint_btn_disable') }}</span>
            </button>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              @click="closeMaintenanceModal"
              class="px-3 py-1.5 rounded bg-gray-900 text-gray-300 hover:text-white border border-gray-800 transition cursor-pointer font-bold"
            >
              {{ t('btn_close') || 'Close' }}
            </button>
            <button
              type="button"
              @click="submitMaintenance('enable')"
              :disabled="maintSubmitting"
              class="px-3.5 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white transition cursor-pointer font-bold flex items-center gap-1.5 shadow-lg"
            >
              <svg v-if="maintSubmitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              <span>{{ server?.is_maintenance ? t('maint_btn_update') : t('maint_btn_enable') }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Terminal / File Manager Unlock (Step-Up Auth) Modal -->
    <TerminalUnlockModal
      :is-open="showTerminalUnlockModal"
      :server="server"
      :user-has-totp="userHasTotp"
      @close="showTerminalUnlockModal = false"
      @unlocked="onTerminalUnlocked"
    />
    <TerminalUnlockModal
      :is-open="showFileManagerUnlockModal"
      mode="file_manager"
      :server="server"
      :user-has-totp="userHasTotp"
      @close="showFileManagerUnlockModal = false"
      @unlocked="onFileManagerUnlocked"
    />

    <!-- Terminal Close Confirm Modal -->
    <TerminalCloseConfirmModal
      :is-open="showTerminalCloseModal"
      @close="showTerminalCloseModal = false"
      @confirm="confirmCloseTerminal"
    />

    <!-- Terminal Lock Confirm Modal -->
    <TerminalLockConfirmModal
      :is-open="showTerminalLockModal"
      :server="server"
      @close="showTerminalLockModal = false"
      @confirm="confirmLockTerminal"
    />

    <!-- Isolated OS Package Task Runner Modal -->
    <AptTaskRunnerModal
      :is-open="aptRunnerOpen"
      :server-id="currentServerId"
      :hostname="server?.hostname"
      :task-id="aptTaskId"
      :task-unit="aptTaskUnit"
      :task-detail="aptTaskDetail"
      :started-at="aptTaskStartedAt"
      @close="aptRunnerOpen = false"
      @completed="onAptTaskCompleted"
      @trigger-upgrade="triggerOSUpgrade"
      @trigger-fix="startAptTask('APT_FIX')"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../i18n'
import { formatBytes, formatUptime, isServerOnline } from '../utils/formatters'
import { useToast, confirmAction } from '../utils/useToast'
import RemoteFileManagerModal from './workspace/RemoteFileManagerModal.vue'
import AptTaskRunnerModal from './workspace/AptTaskRunnerModal.vue'
import WorkspaceOverviewTab from './workspace/tabs/WorkspaceOverviewTab.vue'
import WorkspaceProblemsTab from './workspace/tabs/WorkspaceProblemsTab.vue'
import WorkspaceServicesTab from './workspace/tabs/WorkspaceServicesTab.vue'
import WorkspacePortsTab from './workspace/tabs/WorkspacePortsTab.vue'
import WorkspaceProcessesTab from './workspace/tabs/WorkspaceProcessesTab.vue'
import WorkspaceFirewallTab from './workspace/tabs/WorkspaceFirewallTab.vue'
import WorkspaceAccountsTab from './workspace/tabs/WorkspaceAccountsTab.vue'
import WorkspaceCronTab from './workspace/tabs/WorkspaceCronTab.vue'
import WorkspaceFimTab from './workspace/tabs/WorkspaceFimTab.vue'
import WorkspacePackagesTab from './workspace/tabs/WorkspacePackagesTab.vue'
import WorkspaceSslTab from './workspace/tabs/WorkspaceSslTab.vue'
import WorkspaceLogsTab from './workspace/tabs/WorkspaceLogsTab.vue'
import ServerWorkspaceTerminal from './terminal/ServerWorkspaceTerminal.vue'
import TerminalUnlockModal from './terminal/TerminalUnlockModal.vue'
import TerminalCloseConfirmModal from './terminal/TerminalCloseConfirmModal.vue'
import TerminalLockConfirmModal from './terminal/TerminalLockConfirmModal.vue'

const props = defineProps({
  serverId: Number,
  isOpen: Boolean,
  isMinimized: Boolean,
  initialFloatingTool: String,
  assetsList: {
    type: Array,
    default: () => []
  },
  currentUser: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'minimize', 'switch-server', 'open-terminal', 'server-updated', 'refresh-problems'])

const { t } = useI18n()
const toast = useToast()

const currentServerId = ref(props.serverId)
const isMaximized = ref(false)
const showHostDropdown = ref(false)
const hostSearchQuery = ref('')

const loading = ref(false)
const actionBusy = ref(false)
const server = ref(null)
const activeSubTab = ref('overview')
const initialLogSource = ref('')

const showGuardrailModal = ref(false)
const guardrailAction = ref('reboot') // 'reboot' or 'poweroff'

// Integrated Terminal State (Matches original blueprint)
const isTerminalOpen = ref(false)
const showTerminalUnlockModal = ref(false)
const showTerminalCloseModal = ref(false)
const showTerminalLockModal = ref(false)
const workspaceTerminalRef = ref(null)
const userHasTotp = ref(false)
const terminalLeaseSeconds = ref(0)
let terminalLeaseTimer = null

async function openTerminalModal() {
  if (!server.value || !currentServerId.value) return

  if (isTerminalOpen.value) {
    showTerminalCloseModal.value = true
    return
  }

  try {
    const token = localStorage.getItem('pantau_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`/api/servers/${currentServerId.value}/terminal/status`, { headers })
    const data = await res.json().catch(() => ({}))

    if (!res.ok) {
      toast.error(data.detail || 'Failed to check terminal status')
      return
    }

    if (!data.allow_web_terminal) {
      toast.warning(t('term_disabled_msg') || 'Web Terminal is disabled for this asset.')
      return
    }
    if (!data.can_terminal) {
      toast.error(t('term_no_permission_msg') || 'Access denied: Web Terminal permission is required.')
      return
    }

    if (data.is_unlocked && data.remaining_seconds > 0) {
      isTerminalOpen.value = true
      startLeaseCountdown(data.remaining_seconds)
    } else {
      userHasTotp.value = Boolean(data.user_has_totp)
      showTerminalUnlockModal.value = true
    }
  } catch (err) {
    toast.error('Failed to initialize terminal session: ' + (err.message || 'Error'))
  }
}

function onTerminalUnlocked(payload) {
  isTerminalOpen.value = true
  startLeaseCountdown(payload?.remaining_seconds || 900)
}

function confirmCloseTerminal() {
  workspaceTerminalRef.value?.closeSession()
  showTerminalCloseModal.value = false
  isTerminalOpen.value = false
}

async function confirmLockTerminal() {
  showTerminalLockModal.value = false
  try {
    const token = localStorage.getItem('pantau_token') || ''
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
    await fetch(`/api/servers/${currentServerId.value}/terminal/lock`, {
      method: 'POST',
      headers
    })
  } catch (err) {
    console.error('Failed to lock terminal:', err)
  }
  isTerminalOpen.value = false
  stopLeaseCountdown()
}

function startLeaseCountdown(seconds) {
  stopLeaseCountdown()
  terminalLeaseSeconds.value = seconds
  terminalLeaseTimer = setInterval(() => {
    if (terminalLeaseSeconds.value > 0) {
      terminalLeaseSeconds.value -= 1
    } else {
      stopLeaseCountdown()
      isTerminalOpen.value = false
    }
  }, 1000)
}

function stopLeaseCountdown() {
  if (terminalLeaseTimer) {
    clearInterval(terminalLeaseTimer)
    terminalLeaseTimer = null
  }
}

// Dedicated Floating File Manager State
const showFileManagerModal = ref(false)
const showFileManagerUnlockModal = ref(false)

async function openFileManagerModal() {
  if (!server.value || !currentServerId.value) return
  try {
    const token = localStorage.getItem('pantau_token') || ''
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`/api/servers/${currentServerId.value}/files/status`, { headers })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      toast.error(data.detail || 'Failed to check File Manager status')
      return
    }
    if (!data.can_file_manager) {
      toast.error('Access denied: File Manager permission (can_file_manager) is required.')
      return
    }
    if (data.is_unlocked && data.remaining_seconds > 0) {
      showFileManagerModal.value = true
    } else {
      userHasTotp.value = Boolean(data.user_has_totp)
      showFileManagerUnlockModal.value = true
    }
  } catch (err) {
    toast.error('Failed to initialize File Manager: ' + (err.message || 'Error'))
  }
}

function onFileManagerUnlocked() {
  showFileManagerModal.value = true
}

function handleTerminalFromFm(payload) {
  openTerminalModal()
}

const servicesList = ref([])
const monitoredServicesList = ref([])
const processesList = ref([])
const portsList = ref([])
const accountsList = ref([])
const groupsList = ref([])
const serverProblems = ref([])
const firewallData = ref({ status: 'unknown', rules: [] })
const cronData = ref({ jobs: [] })
const packagesList = ref([])
const sslCertsList = ref([])
const logsList = ref([])
const availableLogsList = ref([])
const fimPathsList = ref([])
const fimEventsList = ref([])

const serviceSearch = ref('')
const processSearch = ref('')

const userPerms = computed(() => {
  if (!props.currentUser) return {}
  if (props.currentUser.is_master_admin || props.currentUser.role === 'operator_utama') {
    return {
      can_terminal: true,
      can_server_control: true,
      can_manage_servers: true,
      can_services: true,
      can_processes: true,
      can_firewall: true,
      can_users_sys: true,
      can_cron: true,
      can_apt: true,
      can_ota: true,
      can_ssl: true,
      can_audit: true,
      can_file_manager: true
    }
  }
  return props.currentUser.permissions || {}
})

const canAccessTab = (tabId) => {
  if (!props.currentUser) return true
  if (props.currentUser.is_master_admin || props.currentUser.role === 'operator_utama') return true
  if (tabId === 'overview' || tabId === 'problems') return true
  if (tabId === 'services') return Boolean(userPerms.value.can_services || props.currentUser?.role === 'viewer')
  if (tabId === 'ports') return Boolean(userPerms.value.can_services || userPerms.value.can_processes || userPerms.value.can_firewall || props.currentUser?.role === 'viewer')
  if (tabId === 'processes') return Boolean(userPerms.value.can_processes)
  if (tabId === 'firewall') return Boolean(userPerms.value.can_firewall)
  if (tabId === 'accounts') return Boolean(userPerms.value.can_users_sys || props.currentUser?.role === 'viewer')
  if (tabId === 'cron') return Boolean(userPerms.value.can_cron || props.currentUser?.role === 'viewer')
  if (tabId === 'packages') return Boolean(userPerms.value.can_apt || props.currentUser?.role === 'viewer')
  if (tabId === 'ssl') return Boolean(userPerms.value.can_ssl || props.currentUser?.role === 'viewer')
  if (tabId === 'logs') return Boolean(userPerms.value.can_audit || userPerms.value.can_services || props.currentUser?.role === 'viewer')
  if (tabId === 'fim') return Boolean(userPerms.value.can_audit || props.currentUser?.role === 'viewer')
  return true
}

const activeSSHSessions = computed(() => {
  const result = []
  for (const acc of accountsList.value) {
    const user = acc.user || acc.name
    for (const s of acc.sessions || []) {
      const from = (s.from || '').trim()
      if (from && !from.startsWith(':') && !from.toLowerCase().startsWith('local')) {
        result.push({
          user,
          tty: s.tty || 'ssh',
          from,
          time: s.time,
        })
      }
    }
  }
  return result
})

const activeNonIgnoredProblemsCount = computed(() => serverProblems.value.filter(p => !p.resolved_at && !p.is_ignored).length)

const subTabs = computed(() => {
  const allTabs = [
    { id: 'overview', label: t('tab_perf') },
    { id: 'problems', label: t('tab_incidents'), badge: activeNonIgnoredProblemsCount.value || null },
    { id: 'services', label: t('ws_tab_services'), badge: monitoredServicesList.value.length || servicesList.value.length || null },
    { id: 'ports', label: t('ws_tab_ports'), badge: portsList.value.length || null },
    { id: 'processes', label: t('tab_tasks'), badge: processesList.value.length || null },
    { id: 'firewall', label: t('tab_firewall') },
    { id: 'accounts', label: t('tab_users_ssh'), badge: activeSSHSessions.value.length || null },
    { id: 'cron', label: t('tab_cron'), badge: cronData.value?.jobs?.length || null },
    { id: 'fim', label: t('tab_fim'), badge: fimPathsList.value.filter(p => ['CHANGED', 'MISSING', 'ERROR'].includes(p.status)).length || null },
    { id: 'packages', label: t('tab_packages'), badge: server.value?.apt_upgradable || packagesList.value.length || null },
    { id: 'ssl', label: t('tab_ssl'), badge: sslCertsList.value.length || null },
    { id: 'logs', label: t('tab_logs') },
  ]
  return allTabs.filter(tab => canAccessTab(tab.id))
})

watch(subTabs, (available) => {
  if (!available.some(t => t.id === activeSubTab.value)) {
    activeSubTab.value = 'overview'
  }
})

const allAssets = computed(() => props.assetsList?.length ? props.assetsList : props.fleetServers)

const filteredHosts = computed(() => {
  if (!hostSearchQuery.value) return allAssets.value
  const q = hostSearchQuery.value.toLowerCase()
  return allAssets.value.filter(
    (h) => h.hostname.toLowerCase().includes(q) || (h.ip_address || '').includes(q)
  )
})

const filteredServices = computed(() => {
  if (!serviceSearch.value) return servicesList.value
  const q = serviceSearch.value.toLowerCase()
  return servicesList.value.filter(
    (s) => (s.name || s.unit || '').toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)
  )
})

const filteredProcesses = computed(() => {
  if (!processSearch.value) return processesList.value
  const q = processSearch.value.toLowerCase()
  return processesList.value.filter(
    (p) => String(p.pid).includes(q) || (p.cmd || p.command || '').toLowerCase().includes(q) || (p.user || '').toLowerCase().includes(q)
  )
})

watch(() => props.serverId, (newId) => {
  if (newId) {
    currentServerId.value = newId
    loadServerData()
  }
})

watch(() => props.initialFloatingTool, (tool) => {
  if (tool === 'terminal') {
    openTerminalModal()
  } else if (tool === 'files') {
    openFileManagerModal()
  } else if (tool === 'maintenance') {
    openMaintenanceModal()
  } else if (tool && ['overview', 'problems', 'services', 'ports', 'processes', 'firewall', 'accounts', 'cron', 'fim', 'packages', 'ssl', 'logs'].includes(tool)) {
    activeSubTab.value = tool
  }
}, { immediate: true })

watch(currentServerId, (newId) => {
  if (newId) {
    loadServerData()
  }
})

async function loadServerData() {
  if (!currentServerId.value) return
  loading.value = true
  const token = localStorage.getItem('pantau_token')
  const headers = { Authorization: `Bearer ${token}` }
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}`, { headers })
    const data = await res.json()
    if (data.ok) {
      server.value = data.server
    }

    // Parallel fetch sub-datasets
    const [svcRes, procRes, portRes, accRes, probRes, fwRes, cronRes, pkgRes, sslRes, logsRes, fimRes] = await Promise.all([
      fetch(`/api/servers/${currentServerId.value}/services`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/processes`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/ports`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/accounts`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/problems`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/firewall`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/cron`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/packages`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/ssl`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/logs`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/fim`, { headers }),
    ])

    const svcData = await svcRes.json()
    const procData = await procRes.json()
    const portData = await portRes.json()
    const accData = await accRes.json()
    const probData = await probRes.json()
    const fwData = await fwRes.json()
    const cronD = await cronRes.json()
    const pkgData = await pkgRes.json()
    const sslData = await sslRes.json()
    const logsData = await logsRes.json()
    const fimData = await fimRes.json()

    servicesList.value = svcData.services || []
    monitoredServicesList.value = svcData.monitored_services || []
    processesList.value = procData.processes || []
    portsList.value = portData.ports || []
    accountsList.value = accData.accounts || []
    groupsList.value = accData.groups || []
    serverProblems.value = probData.problems || []
    firewallData.value = fwData.firewall || { status: 'unknown', rules: [] }
    cronData.value = cronD.cron || { jobs: [] }
    packagesList.value = pkgData.packages || []
    sslCertsList.value = sslData.certs || []
    logsList.value = logsData.logs || []
    availableLogsList.value = logsData.available_logs || []
    fimPathsList.value = fimData.paths || []
    fimEventsList.value = fimData.events || fimData.fim || []
    checkActiveAptTask()
  } catch (err) {
    console.error('Error fetching server workspace data:', err)
  } finally {
    loading.value = false
  }
}

function refreshData() {
  loadServerData()
}

function toggleMaximize() {
  isMaximized.value = !isMaximized.value
}

function handleClose() {
  if (isTerminalOpen.value) {
    showTerminalCloseModal.value = true
    return
  }
  emit('close')
}

function handleBackdropClick() {
  if (isTerminalOpen.value) {
    showTerminalCloseModal.value = true
    return
  }
  emit('close')
}

function selectHost(sid) {
  showHostDropdown.value = false
  if (isTerminalOpen.value) {
    workspaceTerminalRef.value?.closeSession()
  }
  currentServerId.value = sid
  isTerminalOpen.value = false
  stopLeaseCountdown()
  emit('switch-server', sid)
}

function navigateHost(direction) {
  if (!allAssets.value || allAssets.value.length === 0) return
  const currentIndex = allAssets.value.findIndex((s) => s.id === currentServerId.value)
  if (currentIndex === -1) return
  let nextIndex = currentIndex + direction
  if (nextIndex < 0) nextIndex = allAssets.value.length - 1
  if (nextIndex >= allAssets.value.length) nextIndex = 0
  const nextServer = allAssets.value[nextIndex]
  if (nextServer) {
    selectHost(nextServer.id)
  }
}

function handleKeyDown(e) {
  if (!props.isOpen || props.isMinimized) return
  if (e.key === 'Escape') {
    if (showHostDropdown.value) {
      showHostDropdown.value = false
      return
    }
    if (showTerminalLockModal.value) { showTerminalLockModal.value = false; return }
    if (showTerminalCloseModal.value) { showTerminalCloseModal.value = false; return }
    if (showFileManagerUnlockModal.value) { showFileManagerUnlockModal.value = false; return }
    if (showTerminalUnlockModal.value) { showTerminalUnlockModal.value = false; return }
    if (showGuardrailModal.value) { showGuardrailModal.value = false; return }
    if (showMaintenanceModal.value) { showMaintenanceModal.value = false; return }
    if (showFileManagerModal.value) return
    handleClose()
    return
  }
  const tag = (e.target?.tagName || '').toUpperCase()
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag) || e.target?.isContentEditable || e.target?.closest?.('.xterm')) {
    return
  }
  if (e.key === '[') {
    navigateHost(-1)
  } else if (e.key === ']') {
    navigateHost(1)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  if (props.serverId) {
    loadServerData()
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  stopLeaseCountdown()
  stopAptBgPoll()
})

// Mode Pemeliharaan (Maintenance Mode)
const showMaintenanceModal = ref(false)
const maintDurationMinutes = ref(60)
const maintReasonInput = ref('')
const maintSubmitting = ref(false)

function openMaintenanceModal() {
  if (server.value) {
    maintReasonInput.value = server.value.maintenance_reason || ''
  }
  showMaintenanceModal.value = true
}

function closeMaintenanceModal() {
  showMaintenanceModal.value = false
}

function formatMaintenanceDate(val) {
  if (!val) return '-'
  try {
    const d = new Date(val)
    return d.toLocaleString()
  } catch (e) {
    return val
  }
}

async function submitMaintenance(action) {
  maintSubmitting.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/maintenance`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        action: action,
        duration_minutes: maintDurationMinutes.value,
        reason: maintReasonInput.value.trim()
      })
    })
    const data = await res.json()
    if (data.ok && server.value) {
      server.value.is_maintenance = data.is_maintenance ? 1 : 0
      server.value.maintenance_until = data.maintenance_until
      server.value.maintenance_reason = data.maintenance_reason
      closeMaintenanceModal()
      emit('server-updated', server.value)
    } else {
      toast.error(data.detail || data.message || 'Operation failed')
    }
  } catch (err) {
    toast.error('Failed to update maintenance mode: ' + err.message)
  } finally {
    maintSubmitting.value = false
  }
}

const aptRunnerOpen = ref(false)
const aptTaskRunning = ref(false)
const aptTaskId = ref(null)
const aptTaskUnit = ref('APT_UPDATE')
const aptTaskDetail = ref('')
const aptTaskStartedAt = ref(null)
const aptElapsedSec = ref(0)
let aptBgPollTimer = null
let aptElapsedTimer = null

const aptTaskLabel = computed(() => {
  if (aptTaskUnit.value === 'APT_UPDATE') return 'Update OS Package Index'
  if (aptTaskUnit.value === 'APT_UPGRADE' || aptTaskUnit.value === 'APT_UPGRADE_INTERACT') return 'Upgrade OS Packages'
  if (aptTaskUnit.value === 'APT_FIX') return 'Repair OS Packages'
  if (aptTaskUnit.value === 'PKG_UPGRADE') return `Upgrade Package: ${aptTaskDetail.value || ''}`
  if (aptTaskUnit.value === 'PKG_CLEAN') return 'Clean Package Cache'
  return 'OS Package Operation'
})

const aptElapsedFormatted = computed(() => {
  const m = Math.floor(aptElapsedSec.value / 60)
  const s = aptElapsedSec.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function stopAptBgPoll() {
  if (aptBgPollTimer) { clearInterval(aptBgPollTimer); aptBgPollTimer = null }
  if (aptElapsedTimer) { clearInterval(aptElapsedTimer); aptElapsedTimer = null }
}

function startAptBgPoll() {
  stopAptBgPoll()
  const updateElapsed = () => {
    if (!aptTaskStartedAt.value) return
    const ms = typeof aptTaskStartedAt.value === 'number'
      ? aptTaskStartedAt.value
      : Date.parse(String(aptTaskStartedAt.value).endsWith('Z') ? aptTaskStartedAt.value : `${aptTaskStartedAt.value}Z`)
    if (ms && !Number.isNaN(ms)) aptElapsedSec.value = Math.max(0, Math.floor((Date.now() - ms) / 1000))
  }
  updateElapsed()
  aptElapsedTimer = setInterval(updateElapsed, 1000)
  aptBgPollTimer = setInterval(async () => {
    if (!aptTaskRunning.value || aptRunnerOpen.value || !aptTaskId.value) return
    const token = localStorage.getItem('pantau_token') || ''
    try {
      const res = await fetch(`/api/logs/request/${aptTaskId.value}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && (data.status === 'success' || data.status === 'failed')) {
        stopAptBgPoll()
        aptTaskRunning.value = false
        const ok = data.status === 'success'
        toast.notify({
          type: ok ? 'success' : 'error',
          title: ok ? `${aptTaskLabel.value} Completed` : `${aptTaskLabel.value} Failed`,
          message: ok ? 'OS package operation finished. Click to view output.' : 'OS package operation failed. Click to inspect output.',
          serverName: server.value?.hostname || 'Host',
          durationSecs: aptElapsedSec.value,
          desktop: true,
          onClick: () => { aptRunnerOpen.value = true },
        })
        await onAptTaskCompleted({ ok })
      }
    } catch (_) {}
  }, 2500)
}

async function checkActiveAptTask() {
  if (!currentServerId.value || !userPerms.value.can_apt) return
  const token = localStorage.getItem('pantau_token') || ''
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/apt/active`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok && data?.active?.id) {
      aptTaskId.value = data.active.id
      aptTaskUnit.value = data.active.unit
      aptTaskDetail.value = data.active.detail || ''
      aptTaskStartedAt.value = data.active.created_at || Date.now()
      aptTaskRunning.value = true
      startAptBgPoll()
    } else {
      aptTaskRunning.value = false
      stopAptBgPoll()
    }
  } catch (_) {}
}

async function startAptTask(unit, detail = '') {
  if (!currentServerId.value || !isServerOnline(server.value)) return
  try {
    const token = localStorage.getItem('pantau_token') || ''
    const res = await fetch('/api/logs/request', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        server_id: currentServerId.value,
        unit,
        detail: detail || undefined,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      if (res.status === 409) {
        const activeRes = await fetch(`/api/servers/${currentServerId.value}/apt/active`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        const activeData = await activeRes.json().catch(() => ({}))
        if (activeData?.active?.id) {
          aptTaskId.value = activeData.active.id
          aptTaskUnit.value = activeData.active.unit
          aptTaskDetail.value = activeData.active.detail || ''
          aptTaskStartedAt.value = activeData.active.created_at || Date.now()
          aptTaskRunning.value = true
          aptRunnerOpen.value = true
          startAptBgPoll()
          return
        }
      }
      toast.error(data.detail || 'Failed to start OS package operation')
      return
    }
    aptTaskId.value = data.id
    aptTaskUnit.value = unit
    aptTaskDetail.value = detail || ''
    aptTaskStartedAt.value = Date.now()
    aptTaskRunning.value = true
    aptRunnerOpen.value = true
    startAptBgPoll()
  } catch (err) {
    toast.error('Failed to start OS package operation: ' + (err.message || 'Error'))
  }
}

async function triggerOSUpdate() {
  if (!isServerOnline(server.value) || aptTaskRunning.value) return
  await startAptTask('APT_UPDATE')
}

async function triggerOSUpgrade() {
  if (!isServerOnline(server.value) || aptTaskRunning.value || (server.value?.apt_upgradable || 0) <= 0) return
  const ok = await confirmAction({
    title: 'Upgrade OS Packages',
    message: `Upgrade ${server.value?.apt_upgradable || 0} operating system packages on ${server.value?.hostname}?`,
    confirmText: 'Upgrade Packages',
    variant: 'warning',
  })
  if (!ok) return
  await startAptTask('APT_UPGRADE')
}

async function triggerPackageUpgrade(pkgName) {
  if (!pkgName || !isServerOnline(server.value) || aptTaskRunning.value) return
  const ok = await confirmAction({
    title: 'Upgrade Package',
    message: `Upgrade package '${pkgName}' on ${server.value?.hostname}?`,
    confirmText: 'Upgrade Package',
    variant: 'warning',
  })
  if (!ok) return
  await startAptTask('PKG_UPGRADE', pkgName)
}

async function onAptTaskCompleted() {
  aptTaskRunning.value = false
  stopAptBgPoll()
  await loadServerData()
  emit('refresh-problems')
  if (server.value) emit('server-updated', server.value)
}

const guardrailPassword = ref('')
const guardrailTotp = ref('')
const guardrailError = ref('')
const guardrailSubmitting = ref(false)

function openGuardrailConfirm(action) {
  if (!isServerOnline(server.value)) return
  guardrailAction.value = action
  guardrailPassword.value = ''
  guardrailTotp.value = ''
  guardrailError.value = ''
  guardrailSubmitting.value = false
  showGuardrailModal.value = true
}

async function executeGuardrailAction() {
  if (guardrailSubmitting.value || !guardrailPassword.value) return
  guardrailSubmitting.value = true
  guardrailError.value = ''
  const actionName = guardrailAction.value === 'reboot' ? 'reboot_host' : 'poweroff_host'
  try {
    const token = localStorage.getItem('pantau_token') || ''
    const res = await fetch(`/api/servers/${currentServerId.value}/actions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        action: actionName,
        params: {
          password: guardrailPassword.value,
          totp: guardrailTotp.value || undefined,
        },
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      guardrailError.value = data.detail || `Failed (${res.status})`
      return
    }
    showGuardrailModal.value = false
    toast.success(data.message || `Command '${actionName}' queued`)
    loadServerData()
  } catch (err) {
    guardrailError.value = err.message || 'Network error'
  } finally {
    guardrailSubmitting.value = false
  }
}

async function restartService(unitName) {
  const ok = await confirmAction({
    title: 'Restart Service',
    message: t('confirm_restart_service', { unit: unitName }),
    confirmText: 'Restart',
    variant: 'warning',
  })
  if (!ok) return
  await dispatchAction('restart_service', { name: unitName, unit: unitName })
}

async function handleServiceAction({ action, unit }) {
  if (action === 'restart_service') {
    return restartService(unit)
  }
  const verbMap = {
    start_service: 'Start',
    stop_service: 'Stop',
    reload_service: 'Reload',
    enable_service: 'Enable Autostart',
    disable_service: 'Disable Autostart',
  }
  const verb = verbMap[action] || 'Execute'
  const ok = await confirmAction({
    title: `${verb} Service`,
    message: `${verb} systemd service '${unit}' on target host?`,
    confirmText: verb,
    variant: action === 'stop_service' || action === 'disable_service' ? 'danger' : 'warning',
  })
  if (!ok) return
  await dispatchAction(action, { name: unit, unit })
}

function handleMonitoredUpdated({ ok, message }) {
  if (ok) {
    toast.success(message || 'Monitored services updated')
    loadServerData()
  } else {
    toast.error(message || 'Failed to update monitored services')
  }
}

async function handleMonitorPort({ service_name, port, process_name }) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/services/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ service_name, port, process_name, is_core: true }),
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      toast.success(data.message)
      loadServerData()
    } else {
      toast.error(data.detail || 'Failed to monitor port as service')
    }
  } catch (err) {
    toast.error(t('msg_conn_failed') + err.message)
  }
}

async function handleFirewallPort({ port, rule }) {
  const isDeny = rule === 'deny'
  const ok = await confirmAction({
    title: isDeny ? 'Block Port (Firewall)' : 'Allow Port (Firewall)',
    message: `${isDeny ? 'Block' : 'Allow'} traffic on port '${port}' via host firewall?`,
    confirmText: isDeny ? 'Block Port' : 'Allow Port',
    variant: isDeny ? 'danger' : 'warning',
  })
  if (!ok) return
  await dispatchAction('firewall_port_rule', { port, rule })
}

async function handleGenericAction({ action, params }) {
  await dispatchAction(action, params)
}

async function handleFimAck(eventId) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/fim/${eventId}/ack`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (res.ok && data.ok) { toast.success(data.message); loadServerData() }
    else { toast.error(data.detail || 'Failed to acknowledge FIM event') }
  } catch (err) { toast.error(t('msg_conn_failed') + err.message) }
}

async function handleFimUnack(eventId) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/fim/${eventId}/unack`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (res.ok && data.ok) { toast.success(data.message); loadServerData() }
    else { toast.error(data.detail || 'Failed to revert FIM acknowledgment') }
  } catch (err) { toast.error(t('msg_conn_failed') + err.message) }
}

async function handleFimAckAll() {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/fim/ack-all`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await res.json()
    if (res.ok && data.ok) { toast.success(data.message); loadServerData() }
    else { toast.error(data.detail || 'Failed to acknowledge FIM events') }
  } catch (err) { toast.error(t('msg_conn_failed') + err.message) }
}

async function handleUserAction({ action, params }) {
  const uname = params?.username || ''
  if (action === 'user_create') {
    return dispatchAction('user_create', params)
  }
  const verbMap = { user_lock: 'Lock Account', user_unlock: 'Unlock Account', user_delete: 'Delete Account' }
  const ok = await confirmAction({
    title: verbMap[action] || 'User Action',
    message: action === 'user_delete'
      ? `Delete Linux user '${uname}' from target host?`
      : `${verbMap[action] || action} for '${uname}'?`,
    confirmText: verbMap[action] || 'Confirm',
    variant: action === 'user_delete' ? 'danger' : 'warning',
  })
  if (!ok) return
  await dispatchAction(action, params)
}

async function killProcess(payload) {
  const pid = typeof payload === 'object' ? payload.pid : payload
  const signal = typeof payload === 'object' && payload.signal ? payload.signal : 'SIGTERM'
  const pname = typeof payload === 'object' ? payload.pname : ''
  const isKill = signal === 'SIGKILL'
  const msg = isKill
    ? `Force terminate (SIGKILL) process PID ${pid} (${pname || 'process'})?`
    : `Send ${signal} to process PID ${pid} (${pname || 'process'})?`
  const ok = await confirmAction({
    title: 'Process Signal Confirmation',
    message: msg,
    confirmText: `Send ${signal}`,
    variant: isKill ? 'danger' : 'warning',
  })
  if (!ok) return
  await dispatchAction('kill_process', { pid, signal, pname })
}

async function terminateSSHSession(user, tty) {
  const ok = await confirmAction({
    title: 'Terminate SSH Session',
    message: t('confirm_sever_ssh', { user, tty }),
    confirmText: 'Terminate',
    variant: 'danger',
  })
  if (!ok) return
  await dispatchAction('terminate_session', { user, tty })
}

async function terminateSSHSessionFromProblem(problemId) {
  const ok = await confirmAction({
    title: 'Terminate SSH Session',
    message: t('confirm_sever_ssh_incident'),
    confirmText: 'Terminate',
    variant: 'danger',
  })
  if (!ok) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${problemId}/terminate-ssh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      toast.success(t('msg_ssh_sever_sent'))
      loadServerData()
    } else {
      toast.error(t('msg_failed') + (data.detail || 'Error'))
    }
  } catch (err) {
    toast.error(t('msg_conn_failed') + err.message)
  }
}

async function handleWorkspaceProblemAck(problemId) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${problemId}/ack`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      }
    })
    const data = await res.json()
    if (data.ok) {
      loadServerData()
      emit('server-updated')
      emit('refresh-problems')
    } else {
      toast.error(data.detail || 'Failed to acknowledge incident')
    }
  } catch (err) {
    console.error('Failed to acknowledge problem in workspace:', err)
  }
}

async function dispatchAction(action, params) {
  const token = localStorage.getItem('pantau_token')
  actionBusy.value = true
  try {
    const res = await fetch(`/api/servers/${currentServerId.value}/actions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ action, params }),
    })
    const data = await res.json()
    if (data.ok) {
      toast.success(data.message)
      loadServerData()
      // Re-poll after agent executes async command so UI reflects updated state automatically
      setTimeout(() => { if (props.isOpen) loadServerData() }, 1600)
      setTimeout(() => { if (props.isOpen) loadServerData(); actionBusy.value = false }, 3400)
      setTimeout(() => { if (props.isOpen) loadServerData() }, 5500)
    } else {
      actionBusy.value = false
      toast.error(t('msg_failed') + (data.detail || 'Error'))
    }
  } catch (err) {
    actionBusy.value = false
    toast.error(t('msg_conn_failed') + err.message)
  }
}
</script>
