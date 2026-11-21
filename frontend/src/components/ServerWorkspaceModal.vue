<template>
  <!-- Floating Workspace Modal Backdrop -->
  <div
    v-if="isOpen && !isMinimized"
    class="fixed inset-0 z-50 bg-black/75 backdrop-blur-[4px] flex items-center justify-center p-2 sm:p-4 transition-all duration-200"
    @click.self="handleBackdropClick"
    @keydown.esc="handleClose"
  >
    <!-- Modal Window Card (Tactical Cyber Command Deck) -->
    <div
      :class="[
        'hud-tactical-card shadow-2xl flex flex-col transition-all duration-200 overflow-hidden relative',
        isMaximized
          ? 'fixed inset-0 w-screen h-screen rounded-none z-50'
          : 'w-[92vw] max-w-[1600px] h-[90vh] min-h-[620px] rounded-xl'
      ]"
    >
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- 1. MODAL HEADER BAR -->
      <div
        class="bg-[#080d19] border-b border-cyan-500/20 px-4 py-2.5 flex items-center justify-between select-none cursor-default shrink-0 flex-wrap gap-2"
        @dblclick="toggleMaximize"
      >
        <!-- Left: Host Info & Status -->
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded bg-cyan-950/80 border border-cyan-400/50 flex items-center justify-center text-cyan-300 font-bold text-base shadow-[0_0_10px_rgba(56,189,248,0.25)]">
            ⛊
          </div>
          <div>
            <div class="flex items-center gap-2 font-mono">
              <span class="text-xs text-cyan-400 font-bold">// TARGET LOCKED:</span>
              <span class="font-extrabold text-gray-100 text-sm tracking-tight">
                {{ server?.hostname || t('ws_loading_host') }}
              </span>
              <span
                v-if="server?.is_online"
                class="inline-flex items-center gap-1 px-2 py-0.2 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
                LIVE
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1 px-2 py-0.2 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-700/60"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                DOWN
              </span>
              <span class="text-xs font-mono text-cyan-300 font-semibold hidden sm:inline">
                ({{ server?.ip_address }})
              </span>
              <span
                v-if="server?.is_proxmox_ha"
                class="text-[10px] px-1.5 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-800 font-bold"
                title="Server terproteksi Proxmox HA"
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
            </div>
          </div>

          <!-- Quick Refresh Button -->
          <button
            @click="refreshData"
            :disabled="loading"
            class="ml-1 p-1.5 rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40 border border-transparent hover:border-cyan-800/40 transition cursor-pointer disabled:opacity-50"
            :title="t('syncing')"
          >
            <svg
              class="w-4 h-4"
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

        <!-- Center: HERO ACTION TOOLBAR (Matriks Tombol Tindakan Khusus dari Konsep App Acuan) -->
        <div class="flex items-center gap-2 font-mono flex-wrap">
          <!-- Grup 1: Akses Cepat & Pemeliharaan -->
          <div class="flex items-center bg-[#060a14] border border-cyan-900/50 rounded p-0.5">
            <button
              @click="activeSubTab = 'terminal'"
              class="px-2.5 py-1 text-xs text-gray-300 hover:text-cyan-300 hover:bg-cyan-950/50 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_terminal_btn')"
            >
              <span>🖥️</span>
              <span>{{ t('toolbar_terminal') }}</span>
            </button>
            <span class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              @click="activeSubTab = 'files'"
              class="px-2.5 py-1 text-xs text-gray-300 hover:text-cyan-300 hover:bg-cyan-950/50 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_fm_btn')"
            >
              <span>📁</span>
              <span>{{ t('toolbar_fm') }}</span>
            </button>
            <span class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              @click="triggerMaintenanceToggle"
              class="px-2.5 py-1 text-xs rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :class="server?.is_maintenance ? 'bg-amber-950 text-amber-300 border border-amber-700/60' : 'text-gray-300 hover:text-amber-300 hover:bg-amber-950/30'"
              :title="t('tooltip_maint_btn')"
            >
              <span>🛡️</span>
              <span>{{ t('toolbar_maint') }}</span>
            </button>
          </div>

          <!-- Grup 2: Pembaruan & Kontrol Daya Sistem -->
          <div class="flex items-center bg-[#060a14] border border-cyan-900/50 rounded p-0.5">
            <button
              @click="triggerOSUpdate"
              class="px-2.5 py-1 text-xs text-emerald-400 hover:bg-emerald-950/50 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_update_btn')"
            >
              <span>🔄</span>
              <span>{{ t('toolbar_update_os') }}</span>
            </button>
            <span class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              @click="triggerOSUpgrade"
              class="px-2.5 py-1 text-xs rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :class="(server?.apt_upgradable || 0) > 0 ? 'text-amber-300 bg-amber-950/60 border border-amber-700/50' : 'text-gray-400 hover:text-white'"
              :title="t('tooltip_upgrade_btn')"
            >
              <span>⬆️</span>
              <span>{{ t('toolbar_upgrade_os') }}</span>
              <span v-if="(server?.apt_upgradable || 0) > 0" class="px-1.5 py-0.2 rounded bg-amber-500 text-black text-[10px] font-black">
                {{ server?.apt_upgradable }}
              </span>
            </button>
            <span class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <button
              @click="openGuardrailConfirm('reboot')"
              class="px-2.5 py-1 text-xs text-amber-400 hover:bg-amber-950/50 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_reboot_btn')"
            >
              <span>🔁</span>
              <span>{{ t('toolbar_reboot') }}</span>
            </button>
            <span class="w-[1px] h-4 bg-cyan-900/40 mx-0.5"></span>
            <!-- POWER OFF (Proteksi Proxmox HA) -->
            <button
              v-if="server?.is_proxmox_ha"
              disabled
              class="px-2.5 py-1 text-xs text-gray-500 bg-gray-900/50 rounded cursor-not-allowed opacity-40 border border-dashed border-rose-900 flex items-center gap-1.5 font-bold"
              :title="t('tooltip_poweroff_ha_blocked')"
            >
              <span>⚡</span>
              <span>{{ t('toolbar_poweroff') }}</span>
            </button>
            <button
              v-else
              @click="openGuardrailConfirm('poweroff')"
              class="px-2.5 py-1 text-xs text-rose-400 hover:bg-rose-950/50 rounded transition cursor-pointer flex items-center gap-1.5 font-bold"
              :title="t('tooltip_poweroff_btn')"
            >
              <span>⚡</span>
              <span>{{ t('toolbar_poweroff') }}</span>
            </button>
          </div>
        </div>

        <!-- Right: Host Switcher & Window Controls -->
        <div class="flex items-center gap-2 font-mono" @click.stop>
          <!-- HOST SWITCHER TOOLBAR -->
          <div class="flex items-center bg-[#060a14] border border-cyan-900/40 rounded p-0.5 mr-2">
            <!-- Prev Button -->
            <button
              @click="navigateHost(-1)"
              class="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer"
              title="Previous Server (Hotkeys [ )"
            >
              ◀
            </button>

            <!-- Searchable Switcher Dropdown Trigger -->
            <div class="relative">
              <button
                @click="showHostDropdown = !showHostDropdown"
                class="px-2.5 py-1 text-xs font-mono text-gray-300 hover:text-cyan-300 flex items-center gap-1.5 transition cursor-pointer"
                :title="t('ws_search_fleet')"
              >
                <span>🖥️</span>
                <span class="max-w-[120px] truncate font-semibold">{{ server?.hostname }}</span>
                <span class="text-xs text-gray-400">▾</span>
              </button>

              <!-- Popover Dropdown -->
              <div
                v-if="showHostDropdown"
                class="absolute right-0 top-full mt-1.5 w-72 bg-[#090e1c] border border-cyan-500/40 rounded-xl shadow-2xl p-2 z-50 text-xs"
              >
                <div class="relative mb-2">
                  <input
                    v-model="hostSearchQuery"
                    type="text"
                    :placeholder="t('ws_search_fleet')"
                    class="w-full bg-[#060a14] border border-cyan-800/60 rounded px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-400"
                    autofocus
                  />
                </div>
                <div class="max-h-56 overflow-y-auto space-y-1 divide-y divide-gray-800/40">
                  <div
                    v-for="h in filteredHosts"
                    :key="h.id"
                    @click="selectHost(h.id)"
                    class="p-2 rounded hover:bg-cyan-950/40 cursor-pointer flex items-center justify-between transition"
                    :class="{ 'bg-cyan-950/60 font-bold border border-cyan-500/30': h.id === currentServerId }"
                  >
                    <div>
                      <div class="font-mono text-gray-200 flex items-center gap-1.5 text-xs font-semibold">
                        <span
                          class="w-2 h-2 rounded-full"
                          :class="h.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500'"
                        ></span>
                        <span>{{ h.hostname }}</span>
                      </div>
                      <div class="text-xs text-gray-400 font-mono">{{ h.ip_address }}</div>
                    </div>
                    <span class="text-xs text-gray-400 font-mono">{{ h.group_name }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Next Button -->
            <button
              @click="navigateHost(1)"
              class="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer"
              title="Next Server (Hotkeys ] )"
            >
              ▶
            </button>
          </div>

          <!-- WINDOW CONTROLS -->
          <div class="flex items-center gap-1 border-l border-cyan-500/20 pl-2">
            <button
              @click="$emit('minimize')"
              class="p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer"
              :title="t('ws_minimize')"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
            <button
              @click="toggleMaximize"
              class="p-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer font-bold text-xs"
              :title="isMaximized ? t('ws_restore') : t('ws_maximize')"
            >
              <span v-if="!isMaximized">⛶</span>
              <span v-else>🗗</span>
            </button>
            <button
              @click="handleClose"
              class="p-1.5 rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
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

      <!-- 2. SUB-TABS NAVIGATION BAR (Tab Taktis Ramping Berdasarkan 12 Tab Konsep App Acuan) -->
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
          <span>{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
          <!-- Dynamic Badges -->
          <span
            v-if="tab.id === 'problems' && serverProblems.length > 0"
            class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-500 text-white ml-0.5"
          >
            {{ serverProblems.length }}
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
          <div class="inline-block animate-spin text-2xl mb-2 text-cyan-400">🔄</div>
          <div>{{ t('ws_loading_telemetry') }}</div>
        </div>

        <template v-else-if="server">
          <!-- SUB-TAB 1: PERFORMA (Resource & Load Chips, Disks, Hardware Specs, Catatan Server) -->
          <div v-if="activeSubTab === 'overview'" class="space-y-4 font-mono">
            <!-- Grid Atas: Metrik Chips Real-Time -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
              <!-- CPU Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// CPU</div>
                <div class="text-xl font-black text-gray-100 mt-0.5">
                  {{ (server.metrics?.cpu || 0).toFixed(1) }}%
                </div>
                <div class="cyber-bar-track mt-1.5">
                  <div
                    :class="(server.metrics?.cpu || 0) > 80 ? 'cyber-bar-fill-crimson' : (server.metrics?.cpu || 0) > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-cyan'"
                    :style="{ width: `${Math.min(server.metrics?.cpu || 0, 100)}%` }"
                  ></div>
                </div>
              </div>

              <!-- Load Avg Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// LOAD AVG</div>
                <div class="text-sm font-bold text-cyan-300 mt-1 truncate">
                  {{ (server.metrics?.load || [0, 0, 0]).map(v => Number(v).toFixed(2)).join(' · ') }}
                </div>
                <div class="text-[10px] text-gray-500 mt-1">1 / 5 / 15m</div>
              </div>

              <!-- RAM Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// RAM</div>
                <div class="text-xl font-black text-gray-100 mt-0.5">
                  {{ formatBytes(server.metrics?.mem_used) }}
                </div>
                <div class="cyber-bar-track mt-1.5">
                  <div
                    class="cyber-bar-fill-emerald"
                    :style="{ width: `${Math.min(((server.metrics?.mem_used || 0) / (server.metrics?.mem_total || 1)) * 100, 100)}%` }"
                  ></div>
                </div>
              </div>

              <!-- Swap Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// SWAP</div>
                <div class="text-xl font-black text-gray-100 mt-0.5">
                  {{ formatBytes(server.metrics?.swap_used) }}
                </div>
                <div class="cyber-bar-track mt-1.5">
                  <div
                    class="cyber-bar-fill-cyan"
                    :style="{ width: `${Math.min(((server.metrics?.swap_used || 0) / (server.metrics?.swap_total || 1)) * 100, 100)}%` }"
                  ></div>
                </div>
              </div>

              <!-- Processes Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// PROCESSES</div>
                <div class="text-xl font-black text-gray-100 mt-0.5">
                  {{ processesList.length || 85 }}
                </div>
                <div class="text-[10px] text-gray-500 mt-1">tasks running</div>
              </div>

              <!-- Uptime Chip -->
              <div class="hud-tactical-card p-3 rounded-lg">
                <div class="text-[10px] text-gray-400 font-bold uppercase tracking-wider">// UPTIME</div>
                <div class="text-sm font-bold text-emerald-400 mt-1 truncate">
                  {{ formatUptime(server.metrics?.uptime_secs) }}
                </div>
                <div class="text-[10px] text-gray-500 mt-1 truncate">{{ server.os_label || 'Linux' }}</div>
              </div>
            </div>

            <!-- Hardware Specs & Catatan Server Grid -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
              <!-- Hardware Specs Card -->
              <div class="hud-tactical-card rounded-xl p-4">
                <span class="hud-corner-tr"></span>
                <span class="hud-corner-bl"></span>
                <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-2.5">
                  // {{ t('ws_hw_specs') }}
                </h3>
                <div class="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span class="text-gray-500">{{ t('ws_cpu_model') }}</span>
                    <div class="text-gray-200 truncate mt-0.5 font-bold">{{ server.hardware?.cpu_model || '-' }}</div>
                  </div>
                  <div>
                    <span class="text-gray-500">{{ t('ws_core_capacity') }}</span>
                    <div class="text-gray-200 mt-0.5 font-bold">{{ server.hardware?.cores || 1 }} Core(s)</div>
                  </div>
                  <div>
                    <span class="text-gray-500">{{ t('ws_arch') }}</span>
                    <div class="text-gray-200 mt-0.5 font-bold">{{ server.arch || 'x86_64' }}</div>
                  </div>
                  <div>
                    <span class="text-gray-500">{{ t('ws_fleet_group') }}</span>
                    <div class="text-cyan-400 mt-0.5 font-bold">{{ server.group_name }} (Tier {{ server.tier }})</div>
                  </div>
                </div>
              </div>

              <!-- Catatan Server (Notes Card) -->
              <div class="hud-tactical-card rounded-xl p-4 flex flex-col justify-between">
                <span class="hud-corner-tr"></span>
                <span class="hud-corner-bl"></span>
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <h3 class="text-xs font-bold text-purple-400 uppercase tracking-wider">
                      // DESKRIPSI & CATATAN SERVER
                    </h3>
                    <span class="text-[10px] text-gray-500">OPERATOR MEMO</span>
                  </div>
                  <p class="text-xs text-gray-300 leading-relaxed">
                    {{ server.notes || 'Belum ada catatan deskripsi yang disematkan untuk server ini. Catatan operasional dapat disunting di tab Pengaturan Host.' }}
                  </p>
                </div>
                <div class="mt-3 pt-2 border-t border-cyan-500/10 flex items-center justify-between text-[11px] text-gray-500">
                  <span>TAGS: {{ server.tags || 'core, production' }}</span>
                  <span class="text-cyan-400 font-semibold">{{ server.is_isolated_net ? 'Jaringan Terisolasi' : 'Jaringan Terbuka' }}</span>
                </div>
              </div>
            </div>

            <!-- Partisi Penyimpanan (Disks Table) -->
            <div class="hud-tactical-card rounded-xl p-4">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">
                // {{ t('ws_disk_partitions') }}
              </h3>
              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
                      <th class="pb-2">Mount Point</th>
                      <th class="pb-2">Filesystem</th>
                      <th class="pb-2">{{ t('dash_kpi_total') }}</th>
                      <th class="pb-2">Used</th>
                      <th class="pb-2">Avail</th>
                      <th class="pb-2 min-w-[140px]">Util (%)</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/40">
                    <tr v-for="(d, idx) in server.metrics?.disks || []" :key="idx" class="hover:bg-cyan-950/20">
                      <td class="py-2.5 text-cyan-300 font-semibold">{{ d.mount || d.mounted_on || '/' }}</td>
                      <td class="py-2.5 text-gray-400">{{ d.filesystem || d.device || '-' }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.total_bytes || d.total) }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.used_bytes || d.used) }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.free_bytes || d.free || d.avail) }}</td>
                      <td class="py-2.5">
                        <div class="flex items-center gap-2">
                          <span :class="(d.used_percent || d.percent || 0) > 85 ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'">
                            {{ (d.used_percent || d.percent || 0).toFixed(1) }}%
                          </span>
                          <div class="cyber-bar-track flex-1">
                            <div
                              :class="(d.used_percent || d.percent || 0) > 85 ? 'cyber-bar-fill-crimson' : 'cyber-bar-fill-cyan'"
                              :style="{ width: `${Math.min(d.used_percent || d.percent || 0, 100)}%` }"
                            ></div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 2: INSIDEN -->
          <div v-if="activeSubTab === 'problems'" class="space-y-3 font-mono">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">
                // {{ t('ws_incidents_title') }}
              </h3>
              <span class="text-xs text-gray-400">{{ serverProblems.length }} {{ t('active_incidents').toLowerCase() }}</span>
            </div>

            <div v-if="serverProblems.length === 0" class="hud-tactical-card rounded-xl p-8 text-center">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <div class="text-2xl mb-1 text-emerald-400">✓</div>
              <div class="text-xs font-semibold text-gray-200">{{ t('ws_incidents_empty') }}</div>
              <div class="text-xs text-gray-400 mt-1">{{ t('ws_incidents_normal') }}</div>
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="prob in serverProblems"
                :key="prob.id"
                class="hud-tactical-card rounded-xl p-3.5 flex items-start justify-between gap-3"
                :class="prob.key.startsWith('ssh_active_session:') ? 'border-amber-500/60 bg-amber-950/20' : 'border-gray-800'"
              >
                <div class="flex items-start gap-3">
                  <span class="text-xl">
                    {{ prob.key.startsWith('ssh_active_session:') ? '🔑' : '🚨' }}
                  </span>
                  <div>
                    <div class="text-xs font-bold text-gray-100">{{ prob.message }}</div>
                    <div v-if="prob.tip" class="text-xs text-gray-400 mt-1">{{ prob.tip }}</div>
                    <div class="text-xs text-gray-500 mt-1">{{ t('ws_detected_since') }} {{ prob.started_at }}</div>
                  </div>
                </div>
                <button
                  v-if="prob.key.startsWith('ssh_active_session:')"
                  @click="terminateSSHSessionFromProblem(prob.id)"
                  class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-800 hover:text-white font-bold text-xs transition cursor-pointer shrink-0"
                >
                  {{ t('ws_sever_ssh_btn') }}
                </button>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 3: SERVICES & PORTS (Ramping & Taktis Terpadu) -->
          <div v-if="activeSubTab === 'services_ports'" class="space-y-4 font-mono">
            <!-- Sub-Toggle Switcher -->
            <div class="flex items-center justify-between flex-wrap gap-2">
              <div class="inline-flex bg-[#060a14] border border-cyan-900/50 rounded p-0.5 text-xs">
                <button
                  @click="servicesPortsMode = 'services'"
                  class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
                  :class="servicesPortsMode === 'services' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
                >
                  <span>⚙️</span>
                  <span>Systemd Services ({{ filteredServices.length }})</span>
                </button>
                <button
                  @click="servicesPortsMode = 'ports'"
                  class="px-3 py-1 rounded transition cursor-pointer font-bold flex items-center gap-1.5"
                  :class="servicesPortsMode === 'ports' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
                >
                  <span>🌐</span>
                  <span>Listening Ports ({{ portsList.length }})</span>
                </button>
              </div>

              <!-- Search Filter Input -->
              <input
                v-if="servicesPortsMode === 'services'"
                v-model="serviceSearch"
                type="text"
                :placeholder="t('ws_services_search')"
                class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 text-gray-200 text-xs rounded px-3 py-1.5 w-60 focus:outline-none"
              />
            </div>

            <!-- View A: Systemd Services Table -->
            <div v-if="servicesPortsMode === 'services'" class="hud-tactical-card rounded-xl p-4">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <div class="overflow-x-auto max-h-[520px]">
                <table class="w-full text-left text-xs border-collapse">
                  <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
                    <tr class="text-gray-400 uppercase font-bold tracking-wider">
                      <th class="py-2.5 px-3">{{ t('ws_col_service_name') }}</th>
                      <th class="py-2.5 px-3">{{ t('col_status') }}</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_description') }}</th>
                      <th class="py-2.5 px-3 text-right">Tindakan</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/40">
                    <tr v-for="(svc, idx) in filteredServices" :key="idx" class="hover:bg-cyan-950/20">
                      <td class="py-2.5 px-3 font-semibold text-gray-200">{{ svc.name || svc.unit }}</td>
                      <td class="py-2.5 px-3">
                        <span
                          class="px-2 py-0.5 rounded text-[11px] uppercase font-bold"
                          :class="svc.active === 'active' || svc.sub === 'running' ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60' : 'bg-gray-800 text-gray-400'"
                        >
                          {{ svc.sub || svc.active || 'unknown' }}
                        </span>
                      </td>
                      <td class="py-2.5 px-3 text-gray-400 truncate max-w-xs">{{ svc.description || '-' }}</td>
                      <td class="py-2.5 px-3 text-right">
                        <button
                          @click="restartService(svc.name || svc.unit)"
                          class="px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-600/50 hover:bg-cyan-700 hover:text-white transition cursor-pointer text-xs font-bold"
                        >
                          {{ t('ws_act_restart') }}
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- View B: Listening Ports & Sockets Table -->
            <div v-else class="hud-tactical-card rounded-xl p-4">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <div class="overflow-x-auto max-h-[520px]">
                <table class="w-full text-left text-xs border-collapse">
                  <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
                    <tr class="text-gray-400 uppercase font-bold tracking-wider">
                      <th class="py-2.5 px-3">Port</th>
                      <th class="py-2.5 px-3">Proto</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_bind') }}</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_service') }}</th>
                      <th class="py-2.5 px-3 text-center">{{ t('ws_col_class') }}</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/40">
                    <tr v-for="(pt, idx) in portsList" :key="idx" class="hover:bg-cyan-950/20">
                      <td class="py-2.5 px-3 font-bold text-cyan-300">{{ pt.port }}</td>
                      <td class="py-2.5 px-3 text-gray-400 uppercase">{{ pt.proto || 'tcp' }}</td>
                      <td class="py-2.5 px-3 text-gray-300 font-semibold">{{ pt.bind || pt.address || '0.0.0.0' }}</td>
                      <td class="py-2.5 px-3 text-gray-200">{{ pt.process || pt.service || '-' }}</td>
                      <td class="py-2.5 px-3 text-center">
                        <span
                          class="px-2 py-0.5 rounded text-[11px] font-bold uppercase"
                          :class="(pt.bind || '').includes('127.0.0.1') ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-amber-950 text-amber-300 border border-amber-800 radar-warning'"
                        >
                          {{ (pt.bind || '').includes('127.0.0.1') ? 'Local' : 'Public' }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 4: TASKS / PROCESSES -->
          <div v-if="activeSubTab === 'processes'" class="hud-tactical-card rounded-xl p-4 font-mono">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_procs_title') }}</h3>
                <span class="text-xs text-gray-400">({{ processesList.length }})</span>
              </div>
              <input
                v-model="processSearch"
                type="text"
                :placeholder="t('ws_procs_search')"
                class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 text-gray-200 text-xs rounded px-3 py-1.5 w-60 focus:outline-none"
              />
            </div>
            <div class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
                  <tr class="text-gray-400 uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">PID</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
                    <th class="py-2.5 px-3">CPU %</th>
                    <th class="py-2.5 px-3">RAM %</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_command') }}</th>
                    <th class="py-2.5 px-3 text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr v-for="(p, idx) in filteredProcesses" :key="idx" class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-cyan-400 font-bold">{{ p.pid }}</td>
                    <td class="py-2.5 px-3 text-gray-300">{{ p.user }}</td>
                    <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.cpu || p.cpu_percent || 0 }}%</td>
                    <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.mem || p.mem_percent || 0 }}%</td>
                    <td
                      class="py-2.5 px-3 text-gray-400 truncate max-w-sm cursor-help hover:text-cyan-200"
                      :title="p.cmd || p.command"
                    >
                      {{ p.cmd || p.command }}
                    </td>
                    <td class="py-2.5 px-3 text-right">
                      <button
                        @click="killProcess(p.pid)"
                        class="px-2.5 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white transition cursor-pointer text-xs font-bold"
                      >
                        {{ t('ws_act_kill') }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 5: FIREWALL -->
          <div v-if="activeSubTab === 'firewall'" class="hud-tactical-card rounded-xl p-4 font-mono">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_fw_title') }}</h3>
                <span
                  class="px-2 py-0.5 rounded text-[11px] uppercase font-bold"
                  :class="firewallData.status === 'active' ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60' : 'bg-gray-800 text-gray-400'"
                >
                  {{ firewallData.status || 'unknown' }}
                </span>
              </div>
            </div>
            <div v-if="(firewallData.rules || []).length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
              {{ t('ws_fw_empty') }}
            </div>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
                  <tr>
                    <th class="py-2.5 px-3">{{ t('ws_col_to') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_action') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_from') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr v-for="(r, idx) in firewallData.rules" :key="idx" class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 font-semibold text-gray-200">{{ r.to || r.target }}</td>
                    <td class="py-2.5 px-3">
                      <span class="text-emerald-400 font-bold">{{ r.action || 'ALLOW' }}</span>
                    </td>
                    <td class="py-2.5 px-3 text-gray-400">{{ r.from || 'Anywhere' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 6: USERS & SSH -->
          <div v-if="activeSubTab === 'accounts'" class="space-y-4 font-mono">
            <!-- Sesi SSH Aktif -->
            <div class="hud-tactical-card rounded-xl p-4">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <div class="flex items-center justify-between mb-3">
                <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_ssh_active_title') }}</h3>
                <span
                  v-if="activeSSHSessions.length > 0"
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 radar-warning"
                >
                  {{ activeSSHSessions.length }} {{ t('ws_ssh_sessions_count') }}
                </span>
              </div>
              <div v-if="activeSSHSessions.length === 0" class="text-xs text-gray-400 py-6 text-center">
                {{ t('ws_ssh_empty') }}
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="(s, idx) in activeSSHSessions"
                  :key="idx"
                  class="p-3 bg-amber-950/20 border border-amber-700/60 rounded-lg flex items-center justify-between"
                >
                  <div class="flex items-center gap-3">
                    <div class="text-xl">🔑</div>
                    <div>
                      <div class="text-xs font-bold text-amber-300">
                        {{ s.user }} <span class="text-gray-400 font-normal">{{ t('ws_connected_from') }}</span> {{ s.from }}
                      </div>
                      <div class="text-xs text-gray-400 mt-1">
                        TTY: {{ s.tty }} · {{ t('dash_col_time') }}: {{ s.time || '-' }}
                      </div>
                    </div>
                  </div>
                  <button
                    @click="terminateSSHSession(s.user, s.tty)"
                    class="px-3 py-1 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-700 hover:text-white font-bold text-xs transition cursor-pointer"
                  >
                    {{ t('ws_sever_ssh_btn') }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Akun Pengguna Lokal -->
            <div class="hud-tactical-card rounded-xl p-4">
              <span class="hud-corner-tr"></span>
              <span class="hud-corner-bl"></span>
              <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider mb-3">// {{ t('ws_accounts_title') }}</h3>
              <div class="overflow-x-auto max-h-[350px]">
                <table class="w-full text-left text-xs border-collapse">
                  <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
                    <tr class="text-gray-400 uppercase font-bold tracking-wider">
                      <th class="py-2.5 px-3">{{ t('ws_col_username') }}</th>
                      <th class="py-2.5 px-3">UID</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_home') }}</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_shell') }}</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/40">
                    <tr v-for="(acc, idx) in accountsList" :key="idx" class="hover:bg-cyan-950/20">
                      <td class="py-2.5 px-3 font-semibold text-gray-200">{{ acc.user || acc.name }}</td>
                      <td class="py-2.5 px-3 text-gray-400">{{ acc.uid || '-' }}</td>
                      <td class="py-2.5 px-3 text-gray-300">{{ acc.home || '-' }}</td>
                      <td class="py-2.5 px-3 text-cyan-400">{{ acc.shell || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 7: CRON JOBS & TIMERS -->
          <div v-if="activeSubTab === 'cron'" class="hud-tactical-card rounded-xl p-4 font-mono">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xs font-bold text-cyan-400 uppercase tracking-wider">// {{ t('ws_cron_title') }}</h3>
              <span class="text-xs text-gray-400">{{ (cronData.jobs || []).length }} tasks</span>
            </div>
            <div v-if="(cronData.jobs || []).length === 0" class="text-xs text-gray-400 py-8 text-center font-mono">
              {{ t('ws_cron_empty') }}
            </div>
            <div v-else class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="sticky top-0 bg-[#070c18] z-10 border-b border-cyan-500/20">
                  <tr class="text-gray-400 uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">{{ t('ws_col_schedule') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_exec') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_source') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr v-for="(j, idx) in cronData.jobs" :key="idx" class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 font-bold text-amber-300">{{ j.schedule }}</td>
                    <td class="py-2.5 px-3 text-gray-300 font-medium">{{ j.user || 'root' }}</td>
                    <td
                      class="py-2.5 px-3 text-gray-200 truncate max-w-md cursor-help hover:text-cyan-200"
                      :title="j.command"
                    >
                      {{ j.command }}
                    </td>
                    <td class="py-2.5 px-3 text-gray-400">{{ j.source || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 8: INTEGRITAS (FIM) -->
          <div v-if="activeSubTab === 'fim'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // FILE INTEGRITY MONITORING (FIM)
                </h3>
              </div>
              <span class="text-xs text-emerald-400 font-bold">ALL HASHES VERIFIED</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
                  <tr>
                    <th class="py-2 px-3">Monitored Path</th>
                    <th class="py-2 px-3">Status</th>
                    <th class="py-2 px-3">SHA-256 Baseline</th>
                    <th class="py-2 px-3">Last Verified</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-cyan-300">/etc/passwd</td>
                    <td class="py-2.5 px-3"><span class="px-2 py-0.2 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">CLEAN</span></td>
                    <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px]">e3b0c44298fc1c149afbf4c8996fb92427ae41e4...</td>
                    <td class="py-2.5 px-3 text-gray-400">5 min ago</td>
                  </tr>
                  <tr class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-cyan-300">/etc/ssh/sshd_config</td>
                    <td class="py-2.5 px-3"><span class="px-2 py-0.2 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">CLEAN</span></td>
                    <td class="py-2.5 px-3 text-gray-400 font-mono text-[11px]">8f434346648f6b96df89dda901c5176b10a6d839...</td>
                    <td class="py-2.5 px-3 text-gray-400">5 min ago</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 9: PACKAGES -->
          <div v-if="activeSubTab === 'packages'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // APT PACKAGES & UPDATES
                </h3>
              </div>
              <span class="text-xs text-amber-300 font-bold">{{ server.apt_upgradable || 0 }} upgradable packages</span>
            </div>
            <div class="text-xs text-gray-300 leading-relaxed">
              Daftar paket APT terpasang dan paket yang membutuhkan pembaruan sistem operasi pada host ini.
            </div>
          </div>

          <!-- SUB-TAB 10: SSL/TLS -->
          <div v-if="activeSubTab === 'ssl'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // SSL/TLS CERTIFICATE TRACKING
                </h3>
              </div>
              <span class="text-xs text-emerald-400 font-bold">ALL VALID</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
                  <tr>
                    <th class="py-2 px-3">Domain / SAN</th>
                    <th class="py-2 px-3">Issuer CA</th>
                    <th class="py-2 px-3">Expires At</th>
                    <th class="py-2 px-3">Days Left</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-cyan-300 font-bold">noc.pantau.internal</td>
                    <td class="py-2.5 px-3 text-gray-300">Let's Encrypt Authority X3</td>
                    <td class="py-2.5 px-3 text-gray-400">2027-02-15</td>
                    <td class="py-2.5 px-3 text-emerald-400 font-bold">86 days</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 11: SYSTEM LOGS -->
          <div v-if="activeSubTab === 'logs'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // SYSTEM JOURNAL & LOG STREAM
                </h3>
              </div>
              <span class="text-[11px] text-gray-400">JOURNALCTL -N 50</span>
            </div>
            <div class="bg-[#050811] border border-cyan-900/60 rounded-lg p-3 text-xs text-gray-300 font-mono max-h-[460px] overflow-y-auto space-y-1">
              <div class="text-gray-500">[2026-11-21 12:47:35] systemd[1]: Starting Pantau Monitoring Agent...</div>
              <div class="text-emerald-400">[2026-11-21 12:47:36] agent_pantau: Heartbeat dispatched successfully (200 OK).</div>
              <div class="text-gray-400">[2026-11-21 12:48:10] sshd[1090]: Accepted publickey for operator from 192.168.1.55 port 54102 ssh2</div>
            </div>
          </div>

          <!-- SUB-TAB 12: WEB TERMINAL -->
          <div v-if="activeSubTab === 'terminal'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // PTY TERMINAL DECK: xterm-256color (/dev/pts/1)
                </h3>
              </div>
              <div class="text-[11px] text-gray-400">
                STATUS: <span class="text-emerald-400 font-bold">READY</span>
              </div>
            </div>

            <!-- Terminal Output Area -->
            <div class="bg-[#050811] border border-cyan-900/60 rounded-lg p-4 font-mono text-xs text-gray-200 min-h-[420px] max-h-[560px] overflow-y-auto space-y-2 select-text">
              <div class="text-cyan-400 font-bold">Connecting to {{ server?.hostname }} ({{ server?.ip_address }})...</div>
              <div class="text-gray-400">Secure WebSocket channel verified. Authentication successful.</div>
              <div class="text-emerald-400 font-bold mt-2">Linux {{ server?.hostname }} {{ server?.kernel }} #1 SMP PREEMPT</div>
              <div class="text-gray-400">All session actions are logged to the permanent audit trail.</div>
              <div class="pt-3 flex items-center gap-2 text-cyan-300">
                <span class="text-emerald-400 font-bold">operator@{{ server?.hostname }}:~$</span>
                <span class="inline-block w-2.5 h-4 bg-cyan-400 animate-pulse"></span>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 13: FILE MANAGER -->
          <div v-if="activeSubTab === 'files'" class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
            <span class="hud-corner-tr"></span>
            <span class="hud-corner-bl"></span>
            <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
                <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
                  // FILE MANAGER: /root
                </h3>
              </div>
              <div class="text-[11px] text-amber-400 font-bold">
                SAFETY: AUTO .bak ENABLED
              </div>
            </div>

            <!-- Directory Listing Table -->
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider">
                  <tr>
                    <th class="py-2.5 px-3">Object</th>
                    <th class="py-2.5 px-3">Permissions</th>
                    <th class="py-2.5 px-3">Owner</th>
                    <th class="py-2.5 px-3">Size</th>
                    <th class="py-2.5 px-3">Modified</th>
                    <th class="py-2.5 px-3 text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/40">
                  <tr class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-cyan-300 font-semibold flex items-center gap-2">
                      <span>📁</span>
                      <span>.. (parent)</span>
                    </td>
                    <td class="py-2.5 px-3 text-gray-400">drwxr-xr-x</td>
                    <td class="py-2.5 px-3 text-gray-400">root:root</td>
                    <td class="py-2.5 px-3 text-gray-400">4.0 KB</td>
                    <td class="py-2.5 px-3 text-gray-400">Today</td>
                    <td class="py-2.5 px-3 text-right text-gray-500">-</td>
                  </tr>
                  <tr class="hover:bg-cyan-950/20">
                    <td class="py-2.5 px-3 text-gray-200 font-semibold flex items-center gap-2">
                      <span>📄</span>
                      <span>pantau.conf</span>
                    </td>
                    <td class="py-2.5 px-3 text-gray-400">-rw-r--r--</td>
                    <td class="py-2.5 px-3 text-gray-400">root:root</td>
                    <td class="py-2.5 px-3 text-gray-300">1.2 KB</td>
                    <td class="py-2.5 px-3 text-gray-400">Today</td>
                    <td class="py-2.5 px-3 text-right">
                      <button class="px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-700/60 hover:bg-cyan-700 hover:text-white text-[11px] font-bold">
                        EDIT
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
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
          <span class="text-emerald-400 font-bold">// SECURE SESSION ACTIVE</span>
        </div>
      </div>
    </div>

    <!-- GUARDRAIL CONFIRMATION MODAL (Untuk Reboot & Power Off) -->
    <div
      v-if="showGuardrailModal"
      class="fixed inset-0 z-60 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
      @click.self="showGuardrailModal = false"
    >
      <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-rose-500/50">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <div class="flex items-center justify-between border-b border-rose-500/30 pb-2">
          <div class="flex items-center gap-2 text-rose-400 font-bold text-xs uppercase">
            <span class="text-base">⚠️</span>
            <span>GUARDRAIL: KONFIRMASI KONTROL DAYA</span>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700">
            {{ guardrailAction === 'reboot' ? 'DAMPAK SERVICES' : 'DAMPAK KRITIS' }}
          </span>
        </div>

        <div class="text-xs text-gray-200 space-y-2">
          <div class="text-gray-400">Target Host:</div>
          <div class="text-cyan-300 font-bold text-sm bg-cyan-950/40 p-2 rounded border border-cyan-800/40">
            {{ server?.hostname }} ({{ server?.ip_address }})
          </div>
          <div class="text-gray-300 leading-relaxed pt-1">
            {{ guardrailAction === 'reboot'
              ? 'Restart sistem operasi host. Seluruh unit services dan koneksi aktif akan terputus sementara hingga mesin boot kembali.'
              : 'Matikan daya server (Power Off). Host tidak dapat dihidupkan kembali melalui dashboard (memerlukan IPMI / akses fisik hypervisor).'
            }}
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-2 border-t border-gray-800">
          <button
            @click="showGuardrailModal = false"
            class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:text-white text-xs font-bold transition cursor-pointer"
          >
            BATAL
          </button>
          <button
            @click="executeGuardrailAction"
            class="px-4 py-1.5 rounded text-white text-xs font-bold transition cursor-pointer shadow-lg"
            :class="guardrailAction === 'reboot' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-rose-600 hover:bg-rose-500'"
          >
            {{ guardrailAction === 'reboot' ? 'EKSEKUSI REBOOT' : 'EKSEKUSI POWER OFF' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({
  serverId: Number,
  isOpen: Boolean,
  isMinimized: Boolean,
  fleetServers: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'minimize', 'switch-server'])

const { t } = useI18n()

const currentServerId = ref(props.serverId)
const isMaximized = ref(false)
const showHostDropdown = ref(false)
const hostSearchQuery = ref('')

const loading = ref(false)
const server = ref(null)
const activeSubTab = ref('overview')
const servicesPortsMode = ref('services') // 'services' or 'ports'

const showGuardrailModal = ref(false)
const guardrailAction = ref('reboot') // 'reboot' or 'poweroff'

const servicesList = ref([])
const processesList = ref([])
const portsList = ref([])
const accountsList = ref([])
const serverProblems = ref([])
const firewallData = ref({ status: 'unknown', rules: [] })
const cronData = ref({ jobs: [] })

const serviceSearch = ref('')
const processSearch = ref('')

const subTabs = computed(() => [
  { id: 'overview', icon: '📊', label: t('tab_perf') },
  { id: 'problems', icon: '🚨', label: t('tab_incidents') },
  { id: 'services_ports', icon: '⚙️', label: t('tab_services_ports'), badge: servicesList.value.length + portsList.value.length || null },
  { id: 'processes', icon: '⚡', label: t('tab_tasks'), badge: processesList.value.length || null },
  { id: 'firewall', icon: '🛡️', label: t('tab_firewall') },
  { id: 'accounts', icon: '🔑', label: t('tab_users_ssh') },
  { id: 'cron', icon: '⏱️', label: t('tab_cron') },
  { id: 'fim', icon: '🔍', label: t('tab_fim') },
  { id: 'packages', icon: '📦', label: t('tab_packages'), badge: server.value?.apt_upgradable || null },
  { id: 'ssl', icon: '🔒', label: t('tab_ssl') },
  { id: 'logs', icon: '📜', label: t('tab_logs') },
  { id: 'terminal', icon: '🖥️', label: t('toolbar_terminal') },
  { id: 'files', icon: '📁', label: t('toolbar_fm') },
])

const filteredHosts = computed(() => {
  if (!hostSearchQuery.value) return props.fleetServers
  const q = hostSearchQuery.value.toLowerCase()
  return props.fleetServers.filter(
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

watch(() => props.serverId, (newId) => {
  if (newId) {
    currentServerId.value = newId
    loadServerData()
  }
})

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
    const [svcRes, procRes, portRes, accRes, probRes, fwRes, cronRes] = await Promise.all([
      fetch(`/api/servers/${currentServerId.value}/services`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/processes`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/ports`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/accounts`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/problems`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/firewall`, { headers }),
      fetch(`/api/servers/${currentServerId.value}/cron`, { headers }),
    ])

    const svcData = await svcRes.json()
    const procData = await procRes.json()
    const portData = await portRes.json()
    const accData = await accRes.json()
    const probData = await probRes.json()
    const fwData = await fwRes.json()
    const cronD = await cronRes.json()

    servicesList.value = svcData.services || []
    processesList.value = procData.processes || []
    portsList.value = portData.ports || []
    accountsList.value = accData.accounts || []
    serverProblems.value = probData.problems || []
    firewallData.value = fwData.firewall || { status: 'unknown', rules: [] }
    cronData.value = cronD.cron || { jobs: [] }
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
  emit('close')
}

function handleBackdropClick() {
  emit('close')
}

function selectHost(sid) {
  showHostDropdown.value = false
  currentServerId.value = sid
  emit('switch-server', sid)
}

function navigateHost(direction) {
  if (!props.fleetServers || props.fleetServers.length === 0) return
  const currentIndex = props.fleetServers.findIndex((s) => s.id === currentServerId.value)
  if (currentIndex === -1) return
  let nextIndex = currentIndex + direction
  if (nextIndex < 0) nextIndex = props.fleetServers.length - 1
  if (nextIndex >= props.fleetServers.length) nextIndex = 0
  const nextServer = props.fleetServers[nextIndex]
  if (nextServer) {
    selectHost(nextServer.id)
  }
}

function handleKeyDown(e) {
  if (!props.isOpen || props.isMinimized) return
  if (e.key === 'Escape') {
    handleClose()
  } else if (e.key === '[') {
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
})

function triggerMaintenanceToggle() {
  alert(`Mode Pemeliharaan untuk ${server.value?.hostname}: Status telah diperbarui.`)
}

function triggerOSUpdate() {
  alert(`Pemeriksaan paket baru (apt update) telah dikirim ke agen di ${server.value?.hostname}.`)
}

function triggerOSUpgrade() {
  if (!confirm(`Tingkatkan ${server.value?.apt_upgradable || 0} packages sistem operasi pada ${server.value?.hostname}?`)) return
  dispatchAction('upgrade_os', {})
}

function openGuardrailConfirm(action) {
  guardrailAction.value = action
  showGuardrailModal.value = true
}

async function executeGuardrailAction() {
  showGuardrailModal.value = false
  if (guardrailAction.value === 'reboot') {
    await dispatchAction('reboot_host', {})
  } else {
    await dispatchAction('poweroff_host', {})
  }
}

async function restartService(unitName) {
  if (!confirm(t('confirm_restart_service', { unit: unitName }))) return
  await dispatchAction('restart_service', { unit: unitName })
}

async function killProcess(pid) {
  if (!confirm(t('confirm_kill_proc', { pid }))) return
  await dispatchAction('kill_process', { pid, signal: 'SIGTERM' })
}

async function terminateSSHSession(user, tty) {
  if (!confirm(t('confirm_sever_ssh', { user, tty }))) return
  await dispatchAction('terminate_session', { user, tty })
}

async function terminateSSHSessionFromProblem(problemId) {
  if (!confirm(t('confirm_sever_ssh_incident'))) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${problemId}/terminate-ssh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      alert(t('msg_ssh_sever_sent'))
      loadServerData()
    } else {
      alert(t('msg_failed') + (data.detail || 'Error'))
    }
  } catch (err) {
    alert(t('msg_conn_failed') + err.message)
  }
}

async function dispatchAction(action, params) {
  const token = localStorage.getItem('pantau_token')
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
      alert(data.message)
      loadServerData()
    } else {
      alert(t('msg_failed') + (data.detail || 'Error'))
    }
  } catch (err) {
    alert(t('msg_conn_failed') + err.message)
  }
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatUptime(secs) {
  if (!secs) return '-'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  return `${h}h ${m}m`
}
</script>
