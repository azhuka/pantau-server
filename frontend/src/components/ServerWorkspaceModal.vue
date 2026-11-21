<template>
  <!-- Floating Workspace Modal Backdrop -->
  <div
    v-if="isOpen && !isMinimized"
    class="fixed inset-0 z-50 bg-black/70 backdrop-blur-[3px] flex items-center justify-center p-2 sm:p-5 transition-all duration-200"
    @click.self="handleBackdropClick"
    @keydown.esc="handleClose"
  >
    <!-- Modal Window Card -->
    <div
      :class="[
        'bg-[#0b111e] border border-gray-800 shadow-2xl flex flex-col transition-all duration-200 overflow-hidden',
        isMaximized
          ? 'fixed inset-0 w-screen h-screen rounded-none z-50'
          : 'w-[88vw] max-w-[1520px] h-[86vh] min-h-[580px] rounded-2xl'
      ]"
    >
      <!-- MODAL HEADER -->
      <div
        class="bg-[#101726] border-b border-gray-800/80 px-4 py-3 flex items-center justify-between select-none cursor-default shrink-0"
        @dblclick="toggleMaximize"
      >
        <!-- Left: Host Info & Refresh -->
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-base">
            🖥️
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="font-bold text-gray-100 text-base tracking-tight font-mono">
                {{ server?.hostname || t('ws_loading_host') }}
              </span>
              <span
                v-if="server?.is_online"
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950/70 text-emerald-400 border border-emerald-800/50"
              >
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                {{ t('online') }}
              </span>
              <span
                v-else
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-rose-950/70 text-rose-400 border border-rose-800/50"
              >
                <span class="w-2 h-2 rounded-full bg-rose-500"></span>
                {{ t('offline') }}
              </span>
              <span class="text-xs font-mono text-cyan-300 font-semibold hidden sm:inline">
                {{ server?.ip_address }}
              </span>
            </div>
            <div class="text-xs text-gray-400 font-mono flex items-center gap-1.5 mt-0.5">
              <span>{{ server?.os_label || 'Linux' }}</span>
              <span>·</span>
              <span>Kernel {{ server?.kernel || '-' }}</span>
              <span>·</span>
              <span>Agent v{{ server?.agent_version || '-' }}</span>
            </div>
          </div>

          <!-- Quick Refresh Button -->
          <button
            @click="refreshData"
            :disabled="loading"
            class="ml-1 p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800/80 transition cursor-pointer disabled:opacity-50"
            :title="t('syncing')"
          >
            <svg
              class="w-4 h-4"
              :class="{ 'animate-spin text-blue-400': loading }"
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

        <!-- Center / Right: Host Switcher & Window Controls -->
        <div class="flex items-center gap-2" @click.stop>
          <!-- HOST SWITCHER TOOLBAR -->
          <div class="flex items-center bg-[#0d131f] border border-gray-800 rounded-lg p-0.5 mr-2">
            <!-- Prev Button -->
            <button
              @click="navigateHost(-1)"
              class="px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer"
              title="Previous Server (Hotkeys [ )"
            >
              ◀
            </button>

            <!-- Searchable Switcher Dropdown Trigger -->
            <div class="relative">
              <button
                @click="showHostDropdown = !showHostDropdown"
                class="px-2.5 py-1 text-xs font-mono text-gray-300 hover:text-blue-400 flex items-center gap-1.5 transition cursor-pointer"
                :title="t('ws_search_fleet')"
              >
                <span>🖥️</span>
                <span class="max-w-[130px] truncate font-semibold">{{ server?.hostname }}</span>
                <span class="text-xs text-gray-400">▾</span>
              </button>

              <!-- Popover Dropdown -->
              <div
                v-if="showHostDropdown"
                class="absolute right-0 top-full mt-1.5 w-72 bg-[#0e1626] border border-gray-700/80 rounded-xl shadow-2xl p-2 z-50 text-xs"
              >
                <div class="relative mb-2">
                  <input
                    v-model="hostSearchQuery"
                    type="text"
                    :placeholder="t('ws_search_fleet')"
                    class="w-full bg-[#162032] border border-gray-700 rounded-lg px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                    autofocus
                  />
                </div>
                <div class="max-h-56 overflow-y-auto space-y-1 divide-y divide-gray-800/40">
                  <div
                    v-for="h in filteredHosts"
                    :key="h.id"
                    @click="selectHost(h.id)"
                    class="p-2 rounded-lg hover:bg-blue-600/20 cursor-pointer flex items-center justify-between transition"
                    :class="{ 'bg-blue-900/30 font-bold': h.id === currentServerId }"
                  >
                    <div>
                      <div class="font-mono text-gray-200 flex items-center gap-1.5 text-xs font-semibold">
                        <span
                          class="w-2 h-2 rounded-full"
                          :class="h.is_online ? 'bg-emerald-400' : 'bg-rose-500'"
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
              class="px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-800 rounded transition cursor-pointer"
              title="Next Server (Hotkeys ] )"
            >
              ▶
            </button>
          </div>

          <!-- WINDOW CONTROLS -->
          <div class="flex items-center gap-1 border-l border-gray-800 pl-2">
            <!-- Minimize Button -->
            <button
              @click="$emit('minimize')"
              class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer"
              :title="t('ws_minimize')"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>

            <!-- Maximize / Restore Button -->
            <button
              @click="toggleMaximize"
              class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer font-bold text-xs"
              :title="isMaximized ? t('ws_restore') : t('ws_maximize')"
            >
              <span v-if="!isMaximized">⛶</span>
              <span v-else>🗗</span>
            </button>

            <!-- Close Button -->
            <button
              @click="handleClose"
              class="p-1.5 rounded-lg text-gray-400 hover:text-rose-400 hover:bg-rose-950/40 transition cursor-pointer"
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

      <!-- SUB-TABS NAVIGATION BAR -->
      <div class="bg-[#0e1523] border-b border-gray-800 px-4 flex items-center gap-1.5 overflow-x-auto shrink-0 select-none py-2">
        <button
          v-for="tab in subTabs"
          :key="tab.id"
          @click="activeSubTab = tab.id"
          class="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 whitespace-nowrap"
          :class="[
            activeSubTab === tab.id
              ? 'bg-blue-600 text-white shadow-sm font-bold'
              : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
          ]"
        >
          <span>{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
          <!-- Dynamic Badges -->
          <span
            v-if="tab.id === 'problems' && serverProblems.length > 0"
            class="px-2 py-0.5 rounded-full text-xs font-bold bg-rose-500 text-white ml-0.5"
          >
            {{ serverProblems.length }}
          </span>
          <span
            v-else-if="tab.id === 'accounts' && activeSSHSessions.length > 0"
            class="px-2 py-0.5 rounded-full text-xs font-bold bg-amber-500 text-black animate-pulse ml-0.5"
            :title="t('human_intercept_badge')"
          >
            {{ activeSSHSessions.length }}
          </span>
          <span
            v-else-if="tab.badge"
            class="text-xs opacity-80 font-mono ml-0.5"
          >
            ({{ tab.badge }})
          </span>
        </button>
      </div>

      <!-- MODAL CONTENT BODY -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        <!-- Loading State -->
        <div v-if="loading && !server" class="py-24 text-center text-gray-400 text-xs">
          <div class="inline-block animate-spin text-2xl mb-2">🔄</div>
          <div>{{ t('ws_loading_telemetry') }}</div>
        </div>

        <template v-else-if="server">
          <!-- SUB-TAB 1: OVERVIEW -->
          <div v-if="activeSubTab === 'overview'" class="space-y-4">
            <!-- 4 Top Stat Gauges -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <!-- CPU Card -->
              <div class="bg-[#121929] border border-gray-800 p-4 rounded-xl">
                <div class="text-xs text-gray-400 font-medium">{{ t('ws_cpu_util') }}</div>
                <div class="text-2xl font-bold font-mono text-gray-100 mt-1">
                  {{ (server.metrics?.cpu || 0).toFixed(1) }}%
                </div>
                <div class="text-xs text-gray-400 font-mono mt-1">
                  Load: {{ (server.metrics?.load || []).join(' · ') }}
                </div>
              </div>

              <!-- RAM Card -->
              <div class="bg-[#121929] border border-gray-800 p-4 rounded-xl">
                <div class="text-xs text-gray-400 font-medium">{{ t('ws_ram_mem') }}</div>
                <div class="text-2xl font-bold font-mono text-gray-100 mt-1">
                  {{ formatBytes(server.metrics?.mem_used) }}
                </div>
                <div class="text-xs text-gray-400 font-mono mt-1">
                  {{ t('dash_kpi_total') }} {{ formatBytes(server.metrics?.mem_total) }}
                </div>
              </div>

              <!-- Swap Card -->
              <div class="bg-[#121929] border border-gray-800 p-4 rounded-xl">
                <div class="text-xs text-gray-400 font-medium">{{ t('ws_swap_mem') }}</div>
                <div class="text-2xl font-bold font-mono text-gray-100 mt-1">
                  {{ formatBytes(server.metrics?.swap_used) }}
                </div>
                <div class="text-xs text-gray-400 font-mono mt-1">
                  {{ t('dash_kpi_total') }} {{ formatBytes(server.metrics?.swap_total) }}
                </div>
              </div>

              <!-- Uptime Card -->
              <div class="bg-[#121929] border border-gray-800 p-4 rounded-xl">
                <div class="text-xs text-gray-400 font-medium">{{ t('ws_uptime') }}</div>
                <div class="text-lg font-bold font-mono text-emerald-400 mt-1">
                  {{ formatUptime(server.metrics?.uptime_secs) }}
                </div>
                <div class="text-xs text-gray-400 font-mono mt-1">
                  {{ t('col_last_seen') }}: {{ server.last_seen || '-' }}
                </div>
              </div>
            </div>

            <!-- Hardware Specifications Summary -->
            <div v-if="server.hardware" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
              <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider mb-2.5">
                {{ t('ws_hw_specs') }}
              </h3>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div>
                  <span class="text-gray-500">{{ t('ws_cpu_model') }}</span>
                  <div class="text-gray-200 truncate">{{ server.hardware.cpu_model || server.hardware.model || '-' }}</div>
                </div>
                <div>
                  <span class="text-gray-500">{{ t('ws_core_capacity') }}</span>
                  <div class="text-gray-200">{{ server.hardware.cores || server.hardware.cpus || '-' }} Core(s)</div>
                </div>
                <div>
                  <span class="text-gray-500">{{ t('ws_arch') }}</span>
                  <div class="text-gray-200">{{ server.arch || 'x86_64' }}</div>
                </div>
                <div>
                  <span class="text-gray-500">{{ t('ws_fleet_group') }}</span>
                  <div class="text-blue-400">{{ server.group_name }} (Tier {{ server.tier }})</div>
                </div>
              </div>
            </div>

            <!-- Partisi Penyimpanan (Disks Table) -->
            <div class="bg-[#121929] border border-gray-800 rounded-xl p-4">
              <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider mb-3">
                {{ t('ws_disk_partitions') }}
              </h3>
              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs font-mono">
                  <thead>
                    <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                      <th class="pb-2">Mount Point</th>
                      <th class="pb-2">Filesystem</th>
                      <th class="pb-2">{{ t('dash_kpi_total') }}</th>
                      <th class="pb-2">Used</th>
                      <th class="pb-2">Avail</th>
                      <th class="pb-2">Util (%)</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/60">
                    <tr v-for="(d, idx) in server.metrics?.disks || []" :key="idx" class="hover:bg-gray-800/20">
                      <td class="py-2.5 text-blue-400 font-semibold">{{ d.mount || d.mounted_on || '/' }}</td>
                      <td class="py-2.5 text-gray-400">{{ d.filesystem || d.device || '-' }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.total_bytes || d.total) }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.used_bytes || d.used) }}</td>
                      <td class="py-2.5 text-gray-300">{{ formatBytes(d.free_bytes || d.free || d.avail) }}</td>
                      <td class="py-2.5">
                        <span :class="(d.used_percent || d.percent || 0) > 85 ? 'text-rose-400 font-bold' : 'text-emerald-400 font-bold'">
                          {{ (d.used_percent || d.percent || 0).toFixed(1) }}%
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 2: INCIDENTS & PROBLEMS -->
          <div v-if="activeSubTab === 'problems'" class="space-y-3">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">
                {{ t('ws_incidents_title') }}
              </h3>
              <span class="text-xs text-gray-400 font-mono">{{ serverProblems.length }} {{ t('active_incidents').toLowerCase() }}</span>
            </div>

            <div v-if="serverProblems.length === 0" class="bg-[#121929] border border-gray-800 rounded-xl p-8 text-center">
              <div class="text-2xl mb-1">✅</div>
              <div class="text-xs font-semibold text-gray-200">{{ t('ws_incidents_empty') }}</div>
              <div class="text-xs text-gray-400 mt-1">{{ t('ws_incidents_normal') }}</div>
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="prob in serverProblems"
                :key="prob.id"
                class="bg-[#121929] border rounded-xl p-3.5 flex items-start justify-between gap-3"
                :class="prob.key.startsWith('ssh_active_session:') ? 'border-amber-500/50 bg-amber-950/15' : 'border-gray-800'"
              >
                <div class="flex items-start gap-3">
                  <span class="text-xl">
                    {{ prob.key.startsWith('ssh_active_session:') ? '🔑' : '🚨' }}
                  </span>
                  <div>
                    <div class="text-xs font-bold text-gray-100">{{ prob.message }}</div>
                    <div v-if="prob.tip" class="text-xs text-gray-400 mt-1">{{ prob.tip }}</div>
                    <div class="text-xs text-gray-500 font-mono mt-1">{{ t('ws_detected_since') }} {{ prob.started_at }}</div>
                  </div>
                </div>
                <button
                  v-if="prob.key.startsWith('ssh_active_session:')"
                  @click="terminateSSHSessionFromProblem(prob.id)"
                  class="px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs shadow transition cursor-pointer shrink-0"
                >
                  {{ t('ws_sever_ssh_btn') }}
                </button>
              </div>
            </div>
          </div>

          <!-- SUB-TAB 3: SERVICES -->
          <div v-if="activeSubTab === 'services'" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_services_title') }}</h3>
                <span class="text-xs text-gray-400 font-mono">({{ filteredServices.length }}/{{ servicesList.length }})</span>
              </div>
              <input
                v-model="serviceSearch"
                type="text"
                :placeholder="t('ws_services_search')"
                class="bg-[#0b111e] border border-gray-700 text-gray-200 text-xs rounded-lg px-3 py-1.5 w-60 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs font-mono">
                <thead class="sticky top-0 bg-[#162032]">
                  <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">{{ t('ws_col_service_name') }}</th>
                    <th class="py-2.5 px-3">{{ t('col_status') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_description') }}</th>
                    <th class="py-2.5 px-3 text-right">{{ t('col_actions') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/60">
                  <tr v-for="(svc, idx) in filteredServices" :key="idx" class="hover:bg-gray-800/30">
                    <td class="py-2.5 px-3 font-semibold text-gray-200">{{ svc.name || svc.unit }}</td>
                    <td class="py-2.5 px-3">
                      <span
                        class="px-2 py-0.5 rounded text-xs uppercase font-semibold"
                        :class="svc.active === 'active' || svc.sub === 'running' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/40' : 'bg-gray-800 text-gray-400'"
                      >
                        {{ svc.sub || svc.active || 'unknown' }}
                      </span>
                    </td>
                    <td class="py-2.5 px-3 text-gray-400 truncate max-w-xs">{{ svc.description || '-' }}</td>
                    <td class="py-2.5 px-3 text-right">
                      <button
                        @click="restartService(svc.name || svc.unit)"
                        class="px-2.5 py-1 rounded bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600 hover:text-white transition cursor-pointer text-xs font-medium"
                      >
                        {{ t('ws_act_restart') }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 4: PROCESSES & TASKS -->
          <div v-if="activeSubTab === 'processes'" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_procs_title') }}</h3>
                <span class="text-xs text-gray-400 font-mono">({{ processesList.length }})</span>
              </div>
              <input
                v-model="processSearch"
                type="text"
                :placeholder="t('ws_procs_search')"
                class="bg-[#0b111e] border border-gray-700 text-gray-200 text-xs rounded-lg px-3 py-1.5 w-60 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs font-mono">
                <thead class="sticky top-0 bg-[#162032]">
                  <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">PID</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
                    <th class="py-2.5 px-3">CPU %</th>
                    <th class="py-2.5 px-3">RAM %</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_command') }}</th>
                    <th class="py-2.5 px-3 text-right">{{ t('col_actions') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/60">
                  <tr v-for="(p, idx) in filteredProcesses" :key="idx" class="hover:bg-gray-800/30">
                    <td class="py-2.5 px-3 text-blue-400 font-bold">{{ p.pid }}</td>
                    <td class="py-2.5 px-3 text-gray-300">{{ p.user }}</td>
                    <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.cpu || p.cpu_percent || 0 }}%</td>
                    <td class="py-2.5 px-3 text-gray-200 font-semibold">{{ p.mem || p.mem_percent || 0 }}%</td>
                    <td class="py-2.5 px-3 text-gray-400 truncate max-w-sm" :title="p.cmd || p.command">{{ p.cmd || p.command }}</td>
                    <td class="py-2.5 px-3 text-right">
                      <button
                        @click="killProcess(p.pid)"
                        class="px-2.5 py-1 rounded bg-rose-600/20 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white transition cursor-pointer text-xs font-medium"
                      >
                        {{ t('ws_act_kill') }}
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 5: PORTS & SOCKETS -->
          <div v-if="activeSubTab === 'ports'" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_ports_title') }}</h3>
              <span class="text-xs text-gray-400 font-mono">{{ portsList.length }} {{ t('ws_open_ports_count') }}</span>
            </div>
            <div class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs font-mono">
                <thead class="sticky top-0 bg-[#162032]">
                  <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">Port</th>
                    <th class="py-2.5 px-3">Proto</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_bind') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_service') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_class') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/60">
                  <tr v-for="(pt, idx) in portsList" :key="idx" class="hover:bg-gray-800/30">
                    <td class="py-2.5 px-3 font-bold text-blue-400">{{ pt.port }}</td>
                    <td class="py-2.5 px-3 text-gray-400 uppercase">{{ pt.proto || 'tcp' }}</td>
                    <td class="py-2.5 px-3 text-gray-300 font-semibold">{{ pt.bind || pt.address || '0.0.0.0' }}</td>
                    <td class="py-2.5 px-3 text-gray-200">{{ pt.process || pt.service || '-' }}</td>
                    <td class="py-2.5 px-3">
                      <span
                        class="px-2 py-0.5 rounded text-xs font-semibold"
                        :class="(pt.bind || '').includes('127.0.0.1') ? 'bg-gray-800 text-gray-400' : 'bg-amber-950/60 text-amber-300 border border-amber-800/50'"
                      >
                        {{ (pt.bind || '').includes('127.0.0.1') ? 'Local' : 'Public' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 6: FIREWALL -->
          <div v-if="activeSubTab === 'firewall'" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_fw_title') }}</h3>
                <span
                  class="px-2 py-0.5 rounded text-xs uppercase font-bold"
                  :class="firewallData.status === 'active' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-gray-800 text-gray-400'"
                >
                  {{ firewallData.status || 'unknown' }}
                </span>
              </div>
            </div>
            <div v-if="(firewallData.rules || []).length === 0" class="text-xs text-gray-400 py-6 text-center font-mono">
              {{ t('ws_fw_empty') }}
            </div>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-left text-xs font-mono">
                <thead>
                  <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">{{ t('ws_col_to') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_action') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_from') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/60">
                  <tr v-for="(r, idx) in firewallData.rules" :key="idx" class="hover:bg-gray-800/30">
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

          <!-- SUB-TAB 7: CRON & TIMERS -->
          <div v-if="activeSubTab === 'cron'" class="bg-[#121929] border border-gray-800 rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_cron_title') }}</h3>
              <span class="text-xs text-gray-400 font-mono">{{ (cronData.jobs || []).length }}</span>
            </div>
            <div v-if="(cronData.jobs || []).length === 0" class="text-xs text-gray-400 py-6 text-center font-mono">
              {{ t('ws_cron_empty') }}
            </div>
            <div v-else class="overflow-x-auto max-h-[500px]">
              <table class="w-full text-left text-xs font-mono">
                <thead class="sticky top-0 bg-[#162032]">
                  <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                    <th class="py-2.5 px-3">{{ t('ws_col_schedule') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_user') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_exec') }}</th>
                    <th class="py-2.5 px-3">{{ t('ws_col_source') }}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-800/60">
                  <tr v-for="(j, idx) in cronData.jobs" :key="idx" class="hover:bg-gray-800/30">
                    <td class="py-2.5 px-3 font-bold text-amber-300">{{ j.schedule }}</td>
                    <td class="py-2.5 px-3 text-gray-300 font-medium">{{ j.user || 'root' }}</td>
                    <td class="py-2.5 px-3 text-gray-200 truncate max-w-md" :title="j.command">{{ j.command }}</td>
                    <td class="py-2.5 px-3 text-gray-400">{{ j.source || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- SUB-TAB 8: USERS & SSH -->
          <div v-if="activeSubTab === 'accounts'" class="space-y-4">
            <!-- Sesi SSH Aktif -->
            <div class="bg-[#121929] border border-gray-800 rounded-xl p-4">
              <div class="flex items-center justify-between mb-3">
                <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider">{{ t('ws_ssh_active_title') }}</h3>
                <span
                  v-if="activeSSHSessions.length > 0"
                  class="px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-black animate-pulse"
                >
                  {{ activeSSHSessions.length }} {{ t('ws_ssh_sessions_count') }}
                </span>
              </div>
              <div v-if="activeSSHSessions.length === 0" class="text-xs text-gray-400 py-4 text-center font-mono">
                {{ t('ws_ssh_empty') }}
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="(s, idx) in activeSSHSessions"
                  :key="idx"
                  class="p-3 bg-amber-950/20 border border-amber-800/40 rounded-lg flex items-center justify-between"
                >
                  <div class="flex items-center gap-3">
                    <div class="text-xl">🔑</div>
                    <div>
                      <div class="text-xs font-bold text-amber-300 font-mono">
                        {{ s.user }} <span class="text-gray-400 font-normal">{{ t('ws_connected_from') }}</span> {{ s.from }}
                      </div>
                      <div class="text-xs text-gray-400 font-mono mt-1">
                        TTY: {{ s.tty }} · {{ t('dash_col_time') }}: {{ s.time || '-' }}
                      </div>
                    </div>
                  </div>
                  <button
                    @click="terminateSSHSession(s.user, s.tty)"
                    class="px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs shadow transition cursor-pointer"
                  >
                    {{ t('ws_sever_ssh_btn') }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Akun Pengguna Lokal -->
            <div class="bg-[#121929] border border-gray-800 rounded-xl p-4">
              <h3 class="text-xs font-bold text-gray-200 uppercase tracking-wider mb-3">{{ t('ws_accounts_title') }}</h3>
              <div class="overflow-x-auto max-h-[350px]">
                <table class="w-full text-left text-xs font-mono">
                  <thead class="sticky top-0 bg-[#162032]">
                    <tr class="border-b border-gray-800 text-gray-400 text-xs uppercase font-bold tracking-wider">
                      <th class="py-2.5 px-3">{{ t('ws_col_username') }}</th>
                      <th class="py-2.5 px-3">UID</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_home') }}</th>
                      <th class="py-2.5 px-3">{{ t('ws_col_shell') }}</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-800/60">
                    <tr v-for="(acc, idx) in accountsList" :key="idx" class="hover:bg-gray-800/30">
                      <td class="py-2.5 px-3 font-semibold text-gray-200">{{ acc.user || acc.name }}</td>
                      <td class="py-2.5 px-3 text-gray-400">{{ acc.uid || '-' }}</td>
                      <td class="py-2.5 px-3 text-gray-300">{{ acc.home || '-' }}</td>
                      <td class="py-2.5 px-3 text-blue-400">{{ acc.shell || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- MODAL FOOTER -->
      <div class="bg-[#101726] border-t border-gray-800/80 px-4 py-2.5 flex items-center justify-between text-xs text-gray-400 font-mono shrink-0 select-none">
        <div>
          <span>ID: #{{ server?.id }}</span>
          <span class="mx-2">·</span>
          <span>Shortcut: <kbd class="px-1.5 py-0.5 bg-gray-800 rounded text-gray-300 font-bold">[</kbd> Prev / <kbd class="px-1.5 py-0.5 bg-gray-800 rounded text-gray-300 font-bold">]</kbd> Next / <kbd class="px-1.5 py-0.5 bg-gray-800 rounded text-gray-300 font-bold">ESC</kbd> {{ t('shelf_close') }}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-emerald-400 font-semibold">● {{ t('footer_live_synced') }}</span>
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
  { id: 'overview', icon: '📊', label: t('ws_tab_overview') },
  { id: 'problems', icon: '🚨', label: t('ws_tab_incidents') },
  { id: 'services', icon: '⚙️', label: t('ws_tab_services'), badge: servicesList.value.length || null },
  { id: 'processes', icon: '⚡', label: t('ws_tab_processes'), badge: processesList.value.length || null },
  { id: 'ports', icon: '🌐', label: t('ws_tab_ports'), badge: portsList.value.length || null },
  { id: 'firewall', icon: '🛡️', label: t('ws_tab_firewall') },
  { id: 'cron', icon: '⏱️', label: t('ws_tab_cron') },
  { id: 'accounts', icon: '🔑', label: t('ws_tab_accounts') },
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
  if (d > 0) return `${d}h ${h}j ${m}m`
  return `${h}j ${m}m`
}
</script>