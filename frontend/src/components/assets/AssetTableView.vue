<template>
  <div class="space-y-4">
    <!-- TOOLBAR ATAS (Search, Filter, Groups) -->
    <div class="hud-tactical-card relative z-30 p-3.5 px-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// ASSET INFRASTRUCTURE MATRIX</span>
          <span class="text-xs text-cyan-400 font-bold">({{ filteredServers.length }} {{ t('nodes_monitored') }})</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('assets_subtitle') }}
        </p>
      </div>

      <!-- Search & Filters -->
      <div class="flex items-center gap-2.5 flex-wrap font-mono">
        <!-- Quick Status Pills -->
        <div class="flex items-center bg-[#060a14] border border-cyan-900/40 rounded p-0.5 text-xs">
          <button
            @click="statusFilter = 'all'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer font-semibold',
              statusFilter === 'all' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            {{ t('all_statuses') }}
          </button>
          <button
            @click="statusFilter = 'online'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'online' ? 'bg-emerald-950 text-emerald-300 font-bold border border-emerald-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
            {{ t('online') }}
          </button>
          <button
            @click="statusFilter = 'offline'"
            :class="[
              'px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 font-semibold',
              statusFilter === 'offline' ? 'bg-rose-950 text-rose-300 font-bold border border-rose-500/50' : 'text-gray-400 hover:text-gray-200'
            ]"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            {{ t('offline') }}
          </button>
        </div>

        <!-- Column Customizer Dropdown -->
        <ColumnCustomizerDropdown
          :columns="columnsConfig"
          @toggle="toggleColumn"
          @preset="applyColumnPreset"
          @reset="resetColumns"
        />

        <!-- Search Input -->
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search_placeholder')"
            class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 rounded px-3 py-1 text-xs text-gray-100 placeholder-gray-500 w-56 focus:outline-none transition font-mono"
          />
          <span class="absolute right-2.5 top-2 text-xs text-gray-500 pointer-events-none">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </span>
        </div>
      </div>
    </div>

    <!-- HIGH-DENSITY ASSET TELEMETRY MATRIX TABLE -->
    <div class="hud-tactical-card rounded-xl overflow-hidden shadow-2xl mb-8">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="bg-[#070c18]/90 border-b border-cyan-500/20 text-gray-400 font-bold tracking-wider select-none">
              <th v-if="isColVisible('status')" class="py-2 px-2 w-14 text-center">{{ t('col_status') }}</th>
              <th v-if="isColVisible('hostname')" @click="setSort('hostname')" class="py-2 px-2.5 min-w-[150px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_server') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('ip')" class="py-2 px-2 min-w-[110px]">{{ t('col_ip') }}</th>
              <th v-if="isColVisible('platform')" @click="setSort('platform_label')" class="py-2 px-2 min-w-[100px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_platform') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('os')" @click="setSort('os_label')" class="py-2 px-2 min-w-[125px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_os') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('cpu')" @click="setSort('cpu')" class="py-2 px-2 min-w-[95px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_cpu') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('memory')" @click="setSort('mem_pct')" class="py-2 px-2 min-w-[110px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_memory') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('storage')" @click="setSort('disk_pct')" class="py-2 px-2 min-w-[85px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_storage') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('uptime')" @click="setSort('uptime')" class="py-2 px-2 min-w-[75px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_uptime') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('agent')" class="py-2 px-2 min-w-[85px] text-center">{{ t('col_agent') }}</th>
              <th v-if="isColVisible('last_seen')" @click="setSort('last_seen')" class="py-2 px-2 min-w-[80px] cursor-pointer hover:text-cyan-300 transition select-none">
                {{ t('col_last_seen') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <th v-if="isColVisible('actions')" class="py-2 px-2.5 text-right w-32 min-w-[125px]">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="s in paginatedServers"
              :key="s.id"
              class="hover:bg-cyan-950/20 transition-colors group"
            >
              <!-- 1. STATUS -->
              <td v-if="isColVisible('status')" class="py-2 px-2 text-center whitespace-nowrap">
                <span
                  v-if="s.is_maintenance"
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950/80 text-amber-300 border border-amber-600/60"
                  :title="s.maintenance_reason ? `${t('status_maint')}: ${s.maintenance_reason}` : t('tooltip_node_maint')"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                  MAINT
                </span>
                <span
                  v-else-if="s.is_online"
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold"
                  :class="s.danger_count > 0 ? 'bg-rose-950/80 text-rose-300 border border-rose-700/60' : (s.critical_count > 0 ? 'bg-orange-950/80 text-orange-300 border border-orange-700/60' : (s.warning_count > 0 ? 'bg-amber-950/80 text-amber-300 border border-amber-700/60' : 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60'))"
                  :title="t('tooltip_node_online')"
                >
                  <span
                    class="w-1.5 h-1.5 rounded-full"
                    :class="s.danger_count > 0 ? 'bg-rose-400 radar-critical' : (s.critical_count > 0 ? 'bg-orange-400 radar-critical' : (s.warning_count > 0 ? 'bg-amber-400 radar-warning' : 'bg-emerald-400 beacon-live'))"
                  ></span>
                  LIVE
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-700/60"
                  :title="t('tooltip_node_offline')"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-rose-500 radar-critical"></span>
                  DOWN
                </span>
              </td>

              <!-- 2. SERVER (Hostname, Group, Environment) -->
              <td v-if="isColVisible('hostname')" class="py-2 px-2.5 whitespace-nowrap">
                <div class="flex items-center gap-1.5">
                  <span class="font-bold text-gray-100 group-hover:text-cyan-300 transition text-sm">
                    {{ s.hostname }}
                  </span>
                  <span
                    v-if="s.tier === 1"
                    class="inline-flex items-center justify-center p-0.5 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-700/50"
                    :title="t('env_prod')"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                      <polyline points="9 12 11 14 15 10"/>
                    </svg>
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center justify-center p-0.5 rounded bg-slate-900/60 text-slate-400 border border-slate-700/50"
                    :title="t('env_non_prod')"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/>
                      <path d="M8.5 2h7"/>
                      <path d="M7 16h10"/>
                    </svg>
                  </span>
                </div>
                <div class="text-xs text-gray-500 flex items-center gap-1.5 mt-0.5">
                  <span class="inline-flex items-center gap-1">
                    <svg class="w-3 h-3 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
                    </svg>
                    <span>{{ s.group_name || 'DEFAULT' }}</span>
                  </span>
                  <span
                    v-if="s.danger_count > 0"
                    class="text-rose-400 font-bold ml-1 px-1 rounded bg-rose-950/80 border border-rose-700/60 radar-critical"
                    :title="s.danger_msgs || 'Danger'"
                  >
                    ● {{ s.danger_count }} danger
                  </span>
                  <span
                    v-else-if="s.critical_count > 0"
                    class="text-orange-400 font-bold ml-1 px-1 rounded bg-orange-950/80 border border-orange-700/60 radar-critical"
                    :title="s.critical_msgs || 'Critical'"
                  >
                    ● {{ s.critical_count }} critical
                  </span>
                  <span
                    v-else-if="s.warning_count > 0"
                    class="text-amber-400 font-bold ml-1 px-1 rounded bg-amber-950/80 border border-amber-700/60 radar-warning"
                    :title="s.warning_msgs || 'Warning'"
                  >
                    ● {{ s.warning_count }} warning
                  </span>
                  <span
                    v-else-if="s.info_count > 0"
                    class="text-sky-400 font-bold ml-1 px-1 rounded bg-sky-950/80 border border-sky-700/60"
                    :title="s.info_msgs || 'Info'"
                  >
                    ● {{ s.info_count }} info
                  </span>
                </div>
              </td>

              <!-- 3. IP / IFACE -->
              <td v-if="isColVisible('ip')" class="py-2 px-2 whitespace-nowrap">
                <div
                  class="text-cyan-300 font-semibold text-xs cursor-help hover:text-cyan-200"
                  :title="s.ip_address || '-'"
                >
                  {{ s.ip_address || '-' }}
                </div>
                <div v-if="s.net_iface" class="text-[11px] text-gray-500 font-mono">
                  {{ s.net_iface }}
                </div>
              </td>

              <!-- 4. PLATFORM -->
              <td v-if="isColVisible('platform')" class="py-2 px-2 whitespace-nowrap text-gray-300 text-xs">
                <div
                  class="cursor-help"
                  :title="`${s.platform_label || s.platform_type || 'Unknown'} - ${s.hardware_model || s.arch || ''}`"
                >
                  <div class="flex items-center gap-1">
                    <span
                      v-if="s.platform_type === 'lxc'"
                      class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/60 inline-flex items-center gap-1"
                    >
                      <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                      <span>LXC</span>
                    </span>
                    <span
                      v-else-if="s.platform_type === 'baremetal'"
                      class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 inline-flex items-center gap-1"
                    >
                      <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                      <span>BAREMETAL</span>
                    </span>
                    <span
                      v-else-if="s.platform_type === 'vm'"
                      class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-950/80 text-purple-300 border border-purple-700/60 inline-flex items-center gap-1"
                    >
                      <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
                      <span>{{ s.platform_short || 'VM' }}</span>
                    </span>
                    <span v-else class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-900 text-gray-300 border border-gray-700">
                      {{ s.platform_short || 'AUTO' }}
                    </span>
                  </div>
                  <div v-if="s.hardware_model || s.arch" class="text-gray-400 text-[11px] truncate max-w-[125px] mt-0.5 font-mono" :title="s.hardware_model || s.arch">
                    {{ s.hardware_model || s.arch }}
                  </div>
                </div>
              </td>

              <!-- 5. OS & KERNEL -->
              <td v-if="isColVisible('os')" class="py-2 px-2 whitespace-nowrap text-gray-300 text-xs">
                <div class="text-gray-200 font-medium">{{ s.os_label || '-' }}</div>
                <div
                  v-if="s.kernel"
                  class="text-gray-500 text-[11px] truncate max-w-[125px] cursor-help hover:text-cyan-300 transition"
                  :title="s.kernel"
                >
                  {{ s.kernel }}
                </div>
              </td>

              <!-- 6. CPU & LOAD -->
              <td v-if="isColVisible('cpu')" class="py-2 px-2 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs mb-1">
                  <span :class="s.cpu > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.cpu || 0).toFixed(1) }}%</span>
                  <span class="text-gray-500 text-[11px]">L {{ (s.load1 || 0).toFixed(2) }}</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.cpu > 80 ? 'cyber-bar-fill-crimson' : s.cpu > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-cyan'"
                    :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 7. MEMORY (RAM & SWAP) -->
              <td v-if="isColVisible('memory')" class="py-2 px-2 whitespace-nowrap">
                <div class="flex items-center justify-between text-xs mb-1">
                  <span :class="s.mem_pct > 80 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
                  <span class="text-gray-400 text-[11px]">{{ formatBytes(s.mem_used) }}</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.mem_pct > 80 ? 'cyber-bar-fill-crimson' : s.mem_pct > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-emerald'"
                    :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- 8. STORAGE -->
              <td v-if="isColVisible('storage')" class="py-2 px-2 whitespace-nowrap">
                <div class="text-xs text-gray-300 mb-1">
                  <span :class="(s.disk_pct || 0) > 85 ? 'text-rose-400 font-bold' : 'text-gray-200 font-medium'">
                    {{ s.disk_pct || 0 }}%
                  </span>
                  <span class="text-gray-500 ml-1 text-[11px]">/root</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    class="cyber-bar-fill-cyan"
                    :style="{ width: `${s.disk_pct || 0}%` }"
                  ></div>
                </div>
              </td>

              <!-- 9. UPTIME -->
              <td v-if="isColVisible('uptime')" class="py-2 px-2 whitespace-nowrap text-gray-300 text-xs">
                {{ formatUptime(s.uptime_secs) }}
              </td>

              <!-- 10. AGENT & PACKAGES -->
              <td v-if="isColVisible('agent')" class="py-2 px-2 whitespace-nowrap text-center">
                <span v-if="s.agent_version" class="px-2 py-0.5 rounded text-[11px] bg-gray-900 text-gray-300 border border-gray-700/80 font-bold">
                  v{{ s.agent_version }}
                </span>
                <span
                  v-if="s.apt_upgradable > 0"
                  class="ml-1 px-1.5 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 cursor-help"
                  :title="`${s.apt_upgradable} ${t('tooltip_apt_upgradable')}`"
                >
                  {{ s.apt_upgradable }}
                </span>
              </td>

              <!-- 11. LAST SEEN -->
              <td v-if="isColVisible('last_seen')" class="py-2 px-2 whitespace-nowrap text-gray-400 text-xs">
                <div>{{ formatRelativeTime(s.last_seen) }}</div>
              </td>

              <!-- 12. KLASTER TOMBOL TINDAKAN (TACTICAL COMMAND CONTROLLER) -->
              <td v-if="isColVisible('actions')" class="py-2 px-2.5 whitespace-nowrap text-right" @click.stop>
                <div class="inline-flex items-center gap-1 noc-action-dropdown-container relative">
                  <!-- Tombol VIEW (Membuka Jendela Rincian Aset) -->
                  <button
                    v-if="!isViewer"
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="px-2 py-1 rounded bg-cyan-950/80 hover:bg-cyan-700 text-cyan-300 hover:text-white border border-cyan-500/50 text-xs font-bold shadow-[0_0_8px_rgba(56,189,248,0.2)] transition cursor-pointer flex items-center gap-1"
                    :title="t('tooltip_view')"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                    <span>{{ t('btn_view') || 'View' }}</span>
                  </button>
                  <button
                    v-else
                    @click="$emit('open-workspace', s.id, 'overview')"
                    class="w-[26px] h-[26px] min-w-[26px] p-0 flex items-center justify-center rounded bg-cyan-950/80 hover:bg-cyan-700 text-cyan-300 hover:text-white border border-cyan-500/50 transition cursor-pointer"
                    :title="t('tooltip_view')"
                    :aria-label="t('btn_view') || 'View'"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>

                  <!-- Shortcut PROBE INSTAN (Hanya untuk non-viewer yang memiliki izin) -->
                  <button
                    v-if="!isViewer && userPerms.can_probing !== false"
                    @click="onProbeClick(s.id)"
                    :disabled="probingServerId === s.id"
                    class="w-6.5 h-6.5 flex items-center justify-center rounded bg-[#0b1324] hover:bg-emerald-950 text-emerald-400 hover:text-emerald-300 border border-cyan-800/40 transition cursor-pointer disabled:opacity-60"
                    :title="t('tooltip_sync')"
                  >
                    <svg
                      class="w-3.5 h-3.5"
                      :class="{ 'animate-spin text-cyan-300': probingServerId === s.id }"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                      <path d="M3 3v5h5"/>
                      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                      <path d="M16 21h5v-5"/>
                    </svg>
                  </button>

                  <!-- Menu DROPDOWN ⋮ (Hanya tampil jika ada aksi dropdown yang diizinkan) -->
                  <div v-if="hasDropdownActions" class="relative inline-block text-left">
                    <button
                      type="button"
                      @click.stop="toggleDropdown(s, $event)"
                      class="w-6.5 h-6.5 flex items-center justify-center rounded transition cursor-pointer border"
                      :class="activeDropdownId === s.id ? 'bg-cyan-950 text-cyan-300 border-cyan-500/60 shadow-[0_0_8px_rgba(56,189,248,0.25)]' : 'bg-[#0b1324] hover:bg-gray-800 text-gray-400 hover:text-white border-gray-700/80'"
                      :title="t('btn_more') || 'More Actions'"
                      aria-label="Actions"
                    >
                      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="1"/>
                        <circle cx="12" cy="5" r="1"/>
                        <circle cx="12" cy="19" r="1"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </td>
            </tr>

            <!-- EMPTY STATE ROW (Kondisi Bersih Awal) -->
            <tr v-if="filteredServers.length === 0">
              <td :colspan="visibleColumnsCount" class="py-14 px-4 text-center">
                <div class="flex flex-col items-center justify-center gap-2">
                  <svg class="w-8 h-8 text-gray-600 mb-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
                    <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
                    <line x1="6" y1="6" x2="6.01" y2="6"/>
                    <line x1="6" y1="18" x2="6.01" y2="18"/>
                  </svg>
                  <div class="text-sm font-bold text-gray-200 font-mono tracking-wider uppercase">// {{ t('assets_empty_title') }}</div>
                  <div class="text-xs text-gray-400 font-mono max-w-md">{{ t('assets_empty_desc') }}</div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Universal Table Pagination Bar (Hidden if <= 10 items) -->
      <NocTablePagination
        v-model:page="currentPage"
        v-model:pageSize="pageSize"
        :total="sortedServers.length"
        unitLabel="servers"
        :pageSizeOptions="[10, 25, 50, 100, 'all']"
      />
    </div>

    <!-- MODALS: EDIT HOST, EDIT NOTE, INJECT KEY, DELETE HOST -->
    <EditHostModal
      :is-open="isEditHostOpen"
      :server="selectedServer"
      @close="isEditHostOpen = false"
      @updated="onHostUpdated"
    />

    <EditNoteModal
      :is-open="isEditNoteOpen"
      :server="selectedServer"
      @close="isEditNoteOpen = false"
      @updated="onHostUpdated"
    />

    <InjectKeyModal
      :is-open="isInjectKeyOpen"
      :server="selectedServer"
      @close="isInjectKeyOpen = false"
      @success="onKeyInjected"
    />

    <DeleteHostModal
      :is-open="isDeleteHostOpen"
      :server="selectedServer"
      @close="isDeleteHostOpen = false"
      @deleted="onHostDeleted"
    />

    <!-- FLOATING TOAST NOTIFICATION -->
    <div
      v-if="toast.show"
      class="fixed bottom-14 right-6 z-50 flex items-center gap-2.5 px-4 py-2.5 rounded-xl border font-mono text-xs shadow-2xl backdrop-blur-md transition-all select-none"
      :class="{
        'bg-[#0b1b2b]/95 border-cyan-500/70 text-cyan-200': toast.type === 'info',
        'bg-[#062419]/95 border-emerald-500/70 text-emerald-200': toast.type === 'success',
        'bg-[#280c12]/95 border-rose-500/70 text-rose-200': toast.type === 'error'
      }"
    >
      <span class="shrink-0">
        <svg v-if="toast.type === 'success'" class="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <svg v-else-if="toast.type === 'error'" class="w-4 h-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <svg v-else class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
      </span>
      <span class="font-medium">{{ toast.message }}</span>
    </div>

    <!-- Floating Action Dropdown Menu (Teleported to body to eliminate table overflow clipping) -->
    <Teleport to="body">
      <div
        v-if="activeDropdownId && activeDropdownServer"
        @click.stop
        :style="dropdownStyle"
        class="bg-[#080d19] border border-cyan-500/50 rounded-xl shadow-[0_12px_36px_rgba(0,0,0,0.85)] p-1.5 z-[100005] text-xs font-mono backdrop-blur-md text-left transition-all select-none"
      >
        <!-- 1. Edit Host -->
        <button
          v-if="userPerms.can_server_control || userPerms.can_manage_servers"
          type="button"
          @click="openEditHost(activeDropdownServer); closeDropdown()"
          class="w-full px-2.5 py-1.5 rounded hover:bg-cyan-950/70 text-gray-200 hover:text-cyan-300 flex items-center gap-2.5 transition cursor-pointer"
        >
          <svg class="w-3.5 h-3.5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            <path d="m15 5 4 4"/>
          </svg>
          <span>{{ t('act_edit_host') }}</span>
        </button>

        <!-- 2. Edit Host Note -->
        <button
          v-if="userPerms.can_manage_servers || userPerms.can_server_control"
          type="button"
          @click="openEditNote(activeDropdownServer); closeDropdown()"
          class="w-full px-2.5 py-1.5 rounded hover:bg-cyan-950/70 text-gray-200 hover:text-cyan-300 flex items-center gap-2.5 transition cursor-pointer"
        >
          <svg class="w-3.5 h-3.5 text-sky-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" x2="8" y1="13" y2="13"/>
            <line x1="16" x2="8" y1="17" y2="17"/>
            <line x1="10" x2="8" y1="9" y2="9"/>
          </svg>
          <span>{{ t('act_edit_host_note') }}</span>
        </button>

        <!-- 3. Test Connection -->
        <button
          v-if="userPerms.can_server_control || userPerms.can_manage_servers"
          type="button"
          @click="testHostConnection(activeDropdownServer); closeDropdown()"
          class="w-full px-2.5 py-1.5 rounded hover:bg-cyan-950/70 text-gray-200 hover:text-cyan-300 flex items-center gap-2.5 transition cursor-pointer"
        >
          <svg class="w-3.5 h-3.5 text-yellow-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          <span>{{ t('act_test_conn') }}</span>
        </button>

        <!-- 4. Inject Key -->
        <button
          v-if="userPerms.can_server_control"
          type="button"
          @click="openInjectKey(activeDropdownServer); closeDropdown()"
          class="w-full px-2.5 py-1.5 rounded hover:bg-cyan-950/70 text-gray-200 hover:text-cyan-300 flex items-center gap-2.5 transition cursor-pointer"
        >
          <svg class="w-3.5 h-3.5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="7.5" cy="15.5" r="5.5"/>
            <path d="m21 2-9.6 9.6"/>
            <path d="m15.5 7.5 3 3L22 7l-3-3"/>
          </svg>
          <span>{{ t('act_inject_key') }}</span>
        </button>

        <!-- Divider -->
        <div v-if="userPerms.can_server_control" class="border-t border-cyan-950/80 my-1"></div>

        <!-- 5. Delete Host -->
        <button
          v-if="userPerms.can_server_control"
          type="button"
          @click="openDeleteHost(activeDropdownServer); closeDropdown()"
          class="w-full px-2.5 py-1.5 rounded hover:bg-rose-950/40 text-rose-400 hover:text-rose-300 flex items-center gap-2.5 transition cursor-pointer"
        >
          <svg class="w-3.5 h-3.5 text-rose-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18"/>
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
            <line x1="10" x2="10" y1="11" y2="17"/>
            <line x1="14" x2="14" y1="11" y2="17"/>
          </svg>
          <span>{{ t('act_delete_host') }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import EditHostModal from './modals/EditHostModal.vue'
import EditNoteModal from './modals/EditNoteModal.vue'
import InjectKeyModal from './modals/InjectKeyModal.vue'
import DeleteHostModal from './modals/DeleteHostModal.vue'
import ColumnCustomizerDropdown from './ColumnCustomizerDropdown.vue'
import NocTablePagination from '../common/NocTablePagination.vue'

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  },
  probingServerId: {
    type: Number,
    default: null
  },
  currentUser: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['open-workspace', 'probe-node', 'server-updated'])

const { t } = useI18n()

// --- ENTERPRISE COLUMN VISIBILITY & CUSTOMIZER ---
const STORAGE_COLS_KEY = 'pantau_asset_matrix_columns_v1'

const defaultColumns = [
  { id: 'status', key: 'col_status', locked: true, visible: true },
  { id: 'hostname', key: 'col_server', locked: true, visible: true },
  { id: 'ip', key: 'col_ip', locked: false, visible: true },
  { id: 'platform', key: 'col_platform', locked: false, visible: true },
  { id: 'os', key: 'col_os', locked: false, visible: true },
  { id: 'cpu', key: 'col_cpu', locked: false, visible: true },
  { id: 'memory', key: 'col_memory', locked: false, visible: true },
  { id: 'storage', key: 'col_storage', locked: false, visible: true },
  { id: 'uptime', key: 'col_uptime', locked: false, visible: true },
  { id: 'agent', key: 'col_agent', locked: false, visible: true },
  { id: 'last_seen', key: 'col_last_seen', locked: false, visible: true },
  { id: 'actions', key: 'col_actions', locked: true, visible: true }
]

function loadSavedColumnVisibility() {
  try {
    const raw = localStorage.getItem(STORAGE_COLS_KEY)
    if (raw) {
      const savedIds = JSON.parse(raw)
      if (Array.isArray(savedIds)) {
        const idSet = new Set(savedIds)
        return defaultColumns.map(col => ({
          ...col,
          visible: col.locked ? true : idSet.has(col.id)
        }))
      }
    }
  } catch (err) {
    console.warn('Failed to load saved column preference:', err)
  }
  return defaultColumns.map(col => ({ ...col }))
}

const rawColumns = ref(loadSavedColumnVisibility())

const columnsConfig = computed(() => {
  return rawColumns.value.map(col => ({
    ...col,
    label: t(col.key) || col.id
  }))
})

function saveColumnsPreference() {
  try {
    const visibleIds = rawColumns.value.filter(c => c.visible).map(c => c.id)
    localStorage.setItem(STORAGE_COLS_KEY, JSON.stringify(visibleIds))
  } catch (err) {
    console.warn('Failed to save column preference:', err)
  }
}

function isColVisible(colId) {
  const col = rawColumns.value.find(c => c.id === colId)
  return col ? col.visible : true
}

const visibleColumnsCount = computed(() => {
  return rawColumns.value.filter(c => c.visible).length || 1
})

function toggleColumn(colId, visible) {
  const target = rawColumns.value.find(c => c.id === colId)
  if (target && !target.locked) {
    target.visible = visible
    saveColumnsPreference()
  }
}

function applyColumnPreset(presetName) {
  if (presetName === 'all') {
    rawColumns.value.forEach(col => { col.visible = true })
  } else if (presetName === 'perf') {
    const perfCols = new Set(['status', 'hostname', 'cpu', 'memory', 'storage', 'uptime', 'last_seen', 'actions'])
    rawColumns.value.forEach(col => {
      col.visible = col.locked || perfCols.has(col.id)
    })
  } else if (presetName === 'inventory') {
    const invCols = new Set(['status', 'hostname', 'ip', 'platform', 'os', 'agent', 'uptime', 'actions'])
    rawColumns.value.forEach(col => {
      col.visible = col.locked || invCols.has(col.id)
    })
  }
  saveColumnsPreference()
}

function resetColumns() {
  rawColumns.value = defaultColumns.map(col => ({ ...col }))
  saveColumnsPreference()
}

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
      can_ssl: true,
      can_audit: true,
      can_file_manager: true
    }
  }
  return props.currentUser.permissions || {}
})

const isViewer = computed(() => {
  if (!props.currentUser) return true
  const role = (props.currentUser.role || '').toLowerCase()
  return ['viewer', 'guest', 'tamu'].includes(role) || props.currentUser.is_guest === true
})

const hasDropdownActions = computed(() => {
  if (isViewer.value) return false
  return Boolean(userPerms.value.can_server_control || userPerms.value.can_manage_servers)
})

const searchQuery = ref('')
const statusFilter = ref('all') // all, online, offline
const activeDropdownId = ref(null)
const activeDropdownServer = ref(null)
const dropdownStyle = ref({})
const copiedServerId = ref(null)

const isEditHostOpen = ref(false)
const isEditNoteOpen = ref(false)
const isInjectKeyOpen = ref(false)
const isDeleteHostOpen = ref(false)
const selectedServer = ref(null)

const toast = ref({ show: false, type: 'info', message: '' })
let toastTimer = null

function showToast(msg, type = 'info', duration = 3000) {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { show: true, type, message: msg }
  toastTimer = setTimeout(() => {
    toast.value.show = false
  }, duration)
}

function openEditHost(s) {
  closeDropdown()
  selectedServer.value = s
  isEditHostOpen.value = true
}

function openEditNote(s) {
  closeDropdown()
  selectedServer.value = s
  isEditNoteOpen.value = true
}

async function testHostConnection(s) {
  closeDropdown()
  showToast(t('toast_testing_conn') || `Testing connection to ${s.hostname}...`, 'info', 2500)
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${s.id}/test-connection`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      showToast(data.message || data.output || t('toast_conn_success'), 'success', 4000)
    } else {
      showToast(data.error || data.detail || t('toast_conn_failed'), 'error', 4500)
    }
  } catch (err) {
    showToast(t('toast_conn_failed') + ': ' + err.message, 'error', 4500)
  }
}

function openInjectKey(s) {
  closeDropdown()
  selectedServer.value = s
  isInjectKeyOpen.value = true
}

function openDeleteHost(s) {
  closeDropdown()
  selectedServer.value = s
  isDeleteHostOpen.value = true
}

function onHostUpdated(msg) {
  showToast(msg || t('toast_host_updated'), 'success')
  emit('server-updated')
}

function onKeyInjected(msg) {
  showToast(msg || t('toast_key_success'), 'success')
}

function onHostDeleted(msg) {
  showToast(msg || t('toast_host_deleted'), 'success')
  emit('server-updated')
}

function closeDropdown() {
  activeDropdownId.value = null
  activeDropdownServer.value = null
}

function toggleDropdown(s, event) {
  if (activeDropdownId.value === s.id) {
    closeDropdown()
    return
  }
  activeDropdownId.value = s.id
  activeDropdownServer.value = s

  if (event && event.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const vh = window.innerHeight
    const vw = window.innerWidth
    const menuHeight = 220
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
        width: '192px'
      }
    } else {
      dropdownStyle.value = {
        position: 'fixed',
        top: `${Math.max(8, rect.bottom + 4)}px`,
        right: `${rightOffset}px`,
        zIndex: 100005,
        width: '192px'
      }
    }
  }
}

function handleSelectAction(sid, tool) {
  closeDropdown()
  emit('open-workspace', sid, tool)
}

function onProbeClick(sid) {
  closeDropdown()
  emit('probe-node', sid)
}

function copyServerIp(ip, sid) {
  if (!ip) return
  navigator.clipboard.writeText(ip).then(() => {
    copiedServerId.value = sid
    setTimeout(() => {
      if (copiedServerId.value === sid) {
        copiedServerId.value = null
      }
    }, 1500)
  }).catch(() => {})
}

function handleKeydown(e) {
  if (e.key === 'Escape') {
    closeDropdown()
  }
}

onMounted(() => {
  window.addEventListener('click', closeDropdown)
  window.addEventListener('scroll', closeDropdown, true)
  window.addEventListener('resize', closeDropdown)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('click', closeDropdown)
  window.removeEventListener('scroll', closeDropdown, true)
  window.removeEventListener('resize', closeDropdown)
  window.removeEventListener('keydown', handleKeydown)
})

const sortCol = ref('id')
const sortAsc = ref(true)

function setSort(col) {
  if (sortCol.value === col) {
    sortAsc.value = !sortAsc.value
  } else {
    sortCol.value = col
    sortAsc.value = true
  }
}

const filteredServers = computed(() => {
  let list = props.servers || []
  if (statusFilter.value === 'online') {
    list = list.filter(s => s.is_online)
  } else if (statusFilter.value === 'offline') {
    list = list.filter(s => !s.is_online)
  }

  if (!searchQuery.value.trim()) return list
  const q = searchQuery.value.toLowerCase()
  return list.filter(s =>
    (s.hostname || '').toLowerCase().includes(q) ||
    (s.ip_address || '').includes(q) ||
    (s.group_name || '').toLowerCase().includes(q) ||
    (s.os_label || '').toLowerCase().includes(q)
  )
})

const sortedServers = computed(() => {
  const list = [...filteredServers.value]
  if (!sortCol.value || sortCol.value === 'id') return list

  return list.sort((a, b) => {
    let aVal = a[sortCol.value]
    let bVal = b[sortCol.value]

    if (sortCol.value === 'uptime') {
      aVal = a.uptime_secs || 0
      bVal = b.uptime_secs || 0
    } else if (sortCol.value === 'last_seen') {
      aVal = a.last_seen ? new Date(a.last_seen).getTime() : 0
      bVal = b.last_seen ? new Date(b.last_seen).getTime() : 0
    } else if (sortCol.value === 'hostname') {
      aVal = (a.hostname || '').toLowerCase()
      bVal = (b.hostname || '').toLowerCase()
    } else if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = (bVal || '').toLowerCase()
    }

    if (aVal < bVal) return sortAsc.value ? -1 : 1
    if (aVal > bVal) return sortAsc.value ? 1 : -1
    return 0
  })
})

const pageSize = ref(10)
const currentPage = ref(1)

const paginatedServers = computed(() => {
  if (pageSize.value === 'all') return sortedServers.value
  const limit = parseInt(pageSize.value, 10) || 10
  const start = (currentPage.value - 1) * limit
  return sortedServers.value.slice(start, start + limit)
})

watch([searchQuery, statusFilter], () => {
  currentPage.value = 1
})

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
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatRelativeTime(isoStr) {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return '-'
  const diffSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000))
  if (diffSec < 10) return 'just now'
  if (diffSec < 60) return `${diffSec}s ago`
  const min = Math.floor(diffSec / 60)
  if (min < 60) return `${min}m ago`
  return `${Math.floor(min / 60)}h ago`
}
</script>
