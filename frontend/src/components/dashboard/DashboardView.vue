<template>
  <div class="space-y-4">
    <!-- 1. GLOBAL TACTICAL KPI BANNER (Asymmetric Grid: 220-250px + 1fr + 280-320px) -->
    <div class="dash-kpi-grid">
      <!-- KARTU 1: FLEET ASSETS STATUS (Kompak 220px - 250px) -->
      <a
        href="#fleet"
        @click.prevent="$emit('nav', 'fleet')"
        id="kpi-card-total"
        class="hud-tactical-card p-3.5 px-4 rounded-xl flex flex-col justify-between hover:border-cyan-400/50 transition cursor-pointer group shadow-lg"
        :title="t('dash_open_fleet')"
      >
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>
        
        <div class="flex items-center justify-between mb-1.5">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
            <span>// FLEET INFRASTRUCTURE OVERVIEW</span>
          </div>
          <span class="text-xs text-gray-500 group-hover:text-cyan-400 transition font-mono font-bold">➔</span>
        </div>

        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1.5 font-mono">
            <span class="text-3xl font-extrabold text-gray-100 leading-none tracking-tight">{{ servers.length }}</span>
            <span class="text-[11px] text-cyan-400 font-bold uppercase tracking-wider">{{ t('dash_kpi_host') }}</span>
          </div>
          <div class="flex items-center gap-1.5 font-mono text-xs">
            <span class="px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 flex items-center gap-1" :title="t('online')">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live"></span>
              {{ upCount }} {{ t('dash_kpi_up') }}
            </span>
            <span
              class="px-2 py-0.5 rounded font-bold flex items-center gap-1"
              :class="downCount > 0 ? 'bg-rose-950/80 text-rose-300 border border-rose-700/70 radar-critical' : 'bg-gray-800/80 text-gray-400 border border-gray-700'"
              :title="t('offline')"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="downCount > 0 ? 'bg-rose-400' : 'bg-gray-500'"></span>
              {{ downCount }} {{ t('dash_kpi_down') }}
            </span>
          </div>
        </div>
      </a>

      <!-- KARTU 2: THREAT & ANOMALY MATRIX (1fr - Memanjang & Fleksibel) -->
      <div
        id="kpi-card-prob"
        class="hud-tactical-card p-3.5 px-4 rounded-xl flex flex-col justify-between shadow-lg"
      >
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <div class="flex items-center justify-between mb-2">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2">
            <span
              class="w-2 h-2 rounded-full"
              :class="dangerCount > 0 ? 'bg-rose-400 radar-critical' : (warnCount > 0 ? 'bg-amber-400 radar-warning' : 'bg-emerald-400 beacon-live')"
            ></span>
            <span>// INCIDENT & ANOMALY MATRIX</span>
          </div>
          <div class="text-xs text-gray-400 font-mono">
            {{ t('dash_kpi_total') }}: <strong class="text-cyan-300 font-bold text-sm">{{ activeProblems.length }}</strong>
          </div>
        </div>

        <!-- Severity Tiles Strip (Zabbix Severity Strip 5 Kotak Terbaca Jelas & Proporsional) -->
        <div class="grid grid-cols-5 gap-2 text-center font-mono">
          <!-- Critical -->
          <div
            class="py-1 px-2 rounded border transition cursor-default"
            :class="dangerCount > 0 ? 'bg-rose-950/90 border-rose-500 text-rose-300 font-bold shadow-[0_0_8px_rgba(244,63,94,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_critical')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ dangerCount }}</span>
            <span class="text-[10px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_critical') }}</span>
          </div>

          <!-- High -->
          <div
            class="py-1 px-2 rounded border transition cursor-default"
            :class="avgCount > 0 ? 'bg-orange-950/90 border-orange-500 text-orange-300 font-bold shadow-[0_0_8px_rgba(249,115,22,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_high')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ avgCount }}</span>
            <span class="text-[10px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_high') }}</span>
          </div>

          <!-- Warning -->
          <div
            class="py-1 px-2 rounded border transition cursor-default"
            :class="warnCount > 0 ? 'bg-amber-950/90 border-amber-500 text-amber-300 font-bold shadow-[0_0_8px_rgba(245,158,11,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_warning')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ warnCount }}</span>
            <span class="text-[10px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_warning') }}</span>
          </div>

          <!-- Info -->
          <div
            class="py-1 px-2 rounded border transition cursor-default"
            :class="infoCount > 0 ? 'bg-cyan-950/90 border-cyan-500 text-cyan-300 font-bold shadow-[0_0_8px_rgba(56,189,248,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_info')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ infoCount }}</span>
            <span class="text-[10px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_info') }}</span>
          </div>

          <!-- Ignored -->
          <div
            class="py-1 px-2 rounded border bg-gray-900/40 border-gray-800/80 text-gray-500 cursor-default"
            :title="t('sev_ignored')"
          >
            <span class="text-base font-extrabold leading-tight block">0</span>
            <span class="text-[10px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_ignored') }}</span>
          </div>
        </div>
      </div>

      <!-- KARTU 3: SATELLITE CHRONO & PRECISION CLOCK (Proporsional 280px - 320px) -->
      <div
        id="dashClockWidget"
        class="hud-tactical-card p-3.5 px-4 rounded-xl flex flex-col justify-between shadow-lg cursor-help"
        :title="`${currentTime} (UTC: ${currentUtcTime})`"
      >
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <div class="flex items-center justify-between mb-1">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live"></span>
            <span>// SYSTEM CLOCK & TIME SYNC</span>
          </div>
          <span class="text-[10px] px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 font-mono font-bold border border-cyan-800/50">
            NOC-CLOCK
          </span>
        </div>

        <div class="flex items-center justify-between gap-3">
          <!-- Calendar: Day & Date -->
          <div class="flex flex-col font-mono">
            <span class="text-sm font-bold text-gray-100 leading-tight">{{ clockDayStr }}</span>
            <span class="text-xs text-gray-400 leading-tight mt-0.5">{{ clockDateStr }}</span>
          </div>

          <!-- Subtle Divider -->
          <div class="w-[1px] h-9 bg-cyan-500/20" aria-hidden="true"></div>

          <!-- Digital Clock HH : MM : SS -->
          <div class="flex items-baseline text-2xl font-black text-cyan-400 tracking-wider font-mono">
            <span>{{ clockHours }}</span>
            <span class="text-cyan-500/60 animate-pulse mx-0.5">:</span>
            <span>{{ clockMinutes }}</span>
            <span class="text-cyan-500/60 animate-pulse mx-0.5">:</span>
            <span class="text-cyan-300 text-base font-bold">{{ clockSeconds }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. RECENT INCIDENTS PANEL (MURNI PASIF: Observasi Situasi) -->
    <div id="dash-problems-card" class="hud-tactical-card rounded-xl overflow-hidden shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Header Bar -->
      <div class="bg-[#0b1324] border-b border-cyan-500/20 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2.5 font-mono">
          <span
            class="w-2.5 h-2.5 rounded-full"
            :class="dangerCount > 0 ? 'bg-rose-400 radar-critical' : (warnCount > 0 ? 'bg-amber-400 radar-warning' : 'bg-emerald-400 beacon-live')"
          ></span>
          <h3 class="text-xs font-bold text-gray-100 tracking-wider uppercase">
            // ACTIVE INCIDENTS & ALERTS QUEUE
          </h3>
          <span
            class="px-2 py-0.2 rounded text-[11px] font-bold"
            :class="activeProblems.length > 0 ? 'bg-rose-950/80 text-rose-300 border border-rose-800' : (servers.length === 0 ? 'bg-gray-800/80 text-gray-400 border border-gray-700' : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800')"
          >
            {{ activeProblems.length > 0 ? `${activeProblems.length} ${t('active_incidents')}` : (servers.length === 0 ? t('nav_status_no_nodes') : t('nav_status_all_secure')) }}
          </span>
        </div>

        <button
          @click="$emit('nav', 'fleet')"
          class="text-xs text-cyan-400 hover:text-cyan-300 transition font-mono flex items-center gap-1.5 cursor-pointer font-semibold"
        >
          <span>{{ t('dash_open_fleet') }}</span>
        </button>
      </div>

      <!-- State Kosong / Status Insiden Dinamis -->
      <div
        v-if="activeProblems.length === 0"
        class="p-6 text-center text-xs font-mono flex items-center justify-center gap-2.5 bg-[#070c18]/50"
      >
        <span
          class="w-4 h-4 rounded-full flex items-center justify-center text-xs font-bold"
          :class="servers.length === 0 ? 'bg-gray-800 text-gray-400' : 'bg-emerald-950 text-emerald-400 border border-emerald-700/60'"
        >
          {{ servers.length === 0 ? '○' : '✓' }}
        </span>
        <span class="text-gray-300">
          {{ servers.length === 0
            ? t('dash_incidents_empty_no_servers')
            : t('dash_incidents_empty', { count: servers.length })
          }}
        </span>
      </div>

      <!-- Tabel Insiden Terkini -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="border-b border-cyan-500/20 text-gray-400 bg-[#070c18]/80 uppercase font-bold tracking-wider select-none">
              <th class="py-2.5 px-4 w-28">{{ t('dash_col_time') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('dash_col_server') }}</th>
              <th class="py-2.5 px-3 w-32 text-center">{{ t('dash_col_severity') }}</th>
              <th class="py-2.5 px-4">{{ t('dash_col_description') }}</th>
              <th class="py-2.5 px-4 w-28 text-right">{{ t('dash_col_duration') }}</th>
              <th class="py-2.5 px-3 w-28 text-center">{{ t('col_actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="prob in activeProblems"
              :key="prob.id"
              class="hover:bg-cyan-950/20 transition-colors group"
            >
              <!-- TIME -->
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">
                {{ formatTime(prob.started_at) }}
              </td>

              <!-- SERVER -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2 font-bold text-gray-100 group-hover:text-cyan-300 transition">
                  <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
                  <span>{{ prob.hostname }}</span>
                </div>
              </td>

              <!-- SEVERITY -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="prob.severity === 'danger'"
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950 text-rose-300 border border-rose-700/80 uppercase shadow-[0_0_6px_rgba(244,63,94,0.3)]"
                >
                  {{ t('sev_critical').toUpperCase() }}
                </span>
                <span
                  v-else-if="prob.severity === 'average'"
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-orange-950 text-orange-300 border border-orange-700/80 uppercase shadow-[0_0_6px_rgba(249,115,22,0.3)]"
                >
                  {{ t('sev_high').toUpperCase() }}
                </span>
                <span
                  v-else-if="prob.severity === 'warning'"
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-700/80 uppercase shadow-[0_0_6px_rgba(245,158,11,0.3)]"
                >
                  {{ t('sev_warning').toUpperCase() }}
                </span>
                <span
                  v-else
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-950 text-blue-300 border border-blue-700/80 uppercase shadow-[0_0_6px_rgba(56,189,248,0.3)]"
                >
                  {{ prob.severity || t('sev_info').toUpperCase() }}
                </span>
              </td>

              <!-- DESCRIPTION -->
              <td class="py-2.5 px-4 text-gray-200 font-medium leading-snug">
                <div>{{ prob.message }}</div>
                <div v-if="prob.tip" class="text-[11px] text-gray-400 font-normal mt-0.5 truncate max-w-xl">
                  {{ prob.tip }}
                </div>
              </td>

              <!-- DURATION -->
              <td class="py-2.5 px-4 text-right whitespace-nowrap text-gray-300">
                <span class="px-2 py-0.5 rounded bg-gray-900 border border-gray-700/80 font-bold">
                  {{ calcDuration(prob.started_at) }}
                </span>
              </td>

              <!-- ACTION: OPEN WORKSPACE -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <button
                  @click="$emit('inspect-node', prob.server_id)"
                  class="px-2.5 py-1 rounded bg-cyan-950/80 hover:bg-cyan-800 text-cyan-300 hover:text-white border border-cyan-600/50 transition cursor-pointer text-[11px] font-bold flex items-center justify-center gap-1 mx-auto"
                >
                  <span>INVESTIGATE</span>
                  <span>➔</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. FLEET STATUS & TELEMETRY RADAR -->
    <div id="dash-fleet-card" class="hud-tactical-card rounded-xl overflow-hidden shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Toolbar -->
      <div class="bg-[#0b1324] border-b border-cyan-500/20 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2.5 font-mono">
          <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 beacon-live"></span>
          <div>
            <h3 class="text-xs font-bold text-gray-100 tracking-wider uppercase">
              // FLEET TELEMETRY & PERFORMANCE
            </h3>
          </div>
        </div>

        <div class="flex items-center gap-2.5 font-mono">
          <!-- View Switcher (Tabel vs Grid) -->
          <div class="inline-flex bg-[#060a14] border border-cyan-900/40 rounded p-0.5 text-xs">
            <button
              @click="fleetViewMode = 'table'"
              class="px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="fleetViewMode === 'table' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_table')"
            >
              <span>{{ t('dash_view_table') }}</span>
            </button>
            <button
              @click="fleetViewMode = 'grid'"
              class="px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="fleetViewMode === 'grid' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_grid')"
            >
              <span>{{ t('dash_view_grid') }}</span>
            </button>
          </div>

          <!-- Search Filter -->
          <input
            v-model="fleetFilter"
            type="text"
            :placeholder="t('dash_search_host')"
            class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 rounded px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 w-48 outline-none transition"
          />
        </div>
      </div>

      <!-- VIEW 1: TABEL OPERASIONAL REAL-TIME DASBOR -->
      <div v-if="fleetViewMode === 'table'" class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="border-b border-cyan-500/20 uppercase font-bold text-gray-400 bg-[#070c18]/80 select-none tracking-wider">
              <th class="py-2.5 px-4">{{ t('col_server') }}</th>
              <th class="py-2.5 px-3 text-center">{{ t('col_status') }}</th>
              <th class="py-2.5 px-3 text-center">{{ t('dash_col_env') }}</th>
              <th class="py-2.5 px-4">{{ t('dash_col_platform_ip') }}</th>
              <th class="py-2.5 px-4 text-center">{{ t('col_uptime') }}</th>
              <th class="py-2.5 px-4 text-center">{{ t('col_cpu') }}</th>
              <th class="py-2.5 px-4 text-center">{{ t('col_memory') }}</th>
              <th class="py-2.5 px-4 text-center">{{ t('dash_col_storage') }}</th>
              <th class="py-2.5 px-3 text-center">{{ t('dash_col_incidents') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="s in filteredServers"
              :key="s.id"
              @click="$emit('inspect-node', s.id)"
              class="hover:bg-cyan-950/20 transition-colors cursor-pointer group"
            >
              <!-- Server -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="w-2 h-2 rounded-full" :class="s.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500'"></span>
                  <span class="font-bold text-gray-100 group-hover:text-cyan-300 transition text-sm">{{ s.hostname }}</span>
                  <span class="text-xs text-gray-500 font-normal">({{ s.group_name || 'Default' }})</span>
                </div>
              </td>

              <!-- Status -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-[11px] font-bold"
                  :class="s.is_online ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60' : 'bg-rose-950/80 text-rose-300 border border-rose-700/60'"
                >
                  {{ s.is_online ? t('online').toUpperCase() : t('offline').toUpperCase() }}
                </span>
              </td>

              <!-- Environment (Tier 1 / Tier 2) -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  class="px-1.5 py-0.2 rounded text-[10px] font-bold"
                  :class="s.tier === 1 ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'bg-purple-950 text-purple-300 border border-purple-800'"
                >
                  {{ s.tier === 1 ? 'TIER 1' : 'TIER 2' }}
                </span>
              </td>

              <!-- Platform / IP -->
              <td class="py-2.5 px-4 whitespace-nowrap text-cyan-300 font-semibold text-xs">
                {{ s.ip_address }}
              </td>

              <!-- Uptime -->
              <td class="py-2.5 px-4 text-center whitespace-nowrap text-gray-300 text-xs">
                {{ formatUptime(s.uptime_secs) }}
              </td>

              <!-- CPU (%) -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span :class="s.cpu > 80 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ (s.cpu || 0).toFixed(1) }}%</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.cpu > 80 ? 'cyber-bar-fill-crimson' : s.cpu > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-cyan'"
                    :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- RAM (%) -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span :class="s.mem_pct > 80 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    :class="s.mem_pct > 80 ? 'cyber-bar-fill-crimson' : s.mem_pct > 60 ? 'cyber-bar-fill-amber' : 'cyber-bar-fill-emerald'"
                    :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"
                  ></div>
                </div>
              </td>

              <!-- Storage (%) -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center justify-between gap-2 mb-1">
                  <span :class="(s.disk_pct || 35) > 85 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ s.disk_pct || 35 }}%</span>
                </div>
                <div class="cyber-bar-track">
                  <div
                    class="cyber-bar-fill-cyan"
                    :style="{ width: `${s.disk_pct || 35}%` }"
                  ></div>
                </div>
              </td>

              <!-- Incidents -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="s.active_problems_count > 0"
                  class="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-800 radar-warning"
                >
                  ● {{ s.active_problems_count }}
                </span>
                <span v-else class="text-gray-500 text-xs">-</span>
              </td>
            </tr>

            <!-- Empty State Baris -->
            <tr v-if="filteredServers.length === 0">
              <td colspan="9" class="py-12 px-4 text-center text-gray-400 font-mono text-xs">
                <div class="flex flex-col items-center justify-center gap-1.5">
                  <span class="text-2xl text-gray-600">📡</span>
                  <div class="font-bold text-gray-200">{{ t('fleet_empty_title') }}</div>
                  <div class="text-gray-400 max-w-sm">{{ t('dash_fleet_empty') }}</div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- VIEW 2: KARTU GRID DASBOR (Tactical Radar Node Grid) -->
      <div v-else class="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 bg-[#070c18]/40">
        <!-- Empty State Grid -->
        <div v-if="filteredServers.length === 0" class="col-span-full py-12 text-center text-gray-400 font-mono text-xs">
          <div class="flex flex-col items-center justify-center gap-1.5">
            <span class="text-2xl text-gray-600">📡</span>
            <div class="font-bold text-gray-200">{{ t('fleet_empty_title') }}</div>
            <div class="text-gray-400 max-w-sm">{{ t('dash_fleet_empty') }}</div>
          </div>
        </div>

        <div
          v-for="s in filteredServers"
          :key="s.id"
          @click="$emit('inspect-node', s.id)"
          class="hud-tactical-card p-3.5 rounded-lg transition-all cursor-pointer group flex flex-col justify-between hover:border-cyan-400/60"
        >
          <span class="hud-corner-tr"></span>
          <span class="hud-corner-bl"></span>

          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 truncate">
                <span class="w-2 h-2 rounded-full shrink-0" :class="s.is_online ? 'bg-emerald-400 beacon-live' : 'bg-rose-500'"></span>
                <span class="font-bold text-gray-100 text-sm truncate group-hover:text-cyan-300 transition font-mono">{{ s.hostname }}</span>
              </div>
              <span class="text-[10px] font-mono text-gray-500 uppercase">{{ s.group_name || 'DEFAULT' }}</span>
            </div>
            <div class="text-xs text-cyan-400 font-mono mt-1 truncate font-semibold">{{ s.ip_address }}</div>
          </div>

          <div class="mt-3.5 space-y-2 text-xs font-mono">
            <div>
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span>CPU LOAD</span>
                <span class="text-gray-200 font-bold">{{ (s.cpu || 0).toFixed(1) }}%</span>
              </div>
              <div class="cyber-bar-track">
                <div class="cyber-bar-fill-cyan" :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"></div>
              </div>
            </div>

            <div>
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span>RAM MEM</span>
                <span class="text-gray-200 font-bold">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
              </div>
              <div class="cyber-bar-track">
                <div class="cyber-bar-fill-emerald" :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"></div>
              </div>
            </div>
          </div>

          <div class="mt-3 pt-2 border-t border-cyan-500/10 flex items-center justify-between text-[11px] font-mono text-gray-400">
            <span>UP // {{ formatUptime(s.uptime_secs) }}</span>
            <span v-if="s.active_problems_count > 0" class="text-amber-400 font-bold radar-warning px-1 rounded">● {{ s.active_problems_count }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  },
  problems: {
    type: Array,
    default: () => []
  }
})

defineEmits(['inspect-node', 'nav'])

const { t, locale } = useI18n()

const fleetViewMode = ref('table') // 'table' or 'grid'
const fleetFilter = ref('')

// Clock state
const clockDayStr = ref('')
const clockDateStr = ref('')
const clockHours = ref('00')
const clockMinutes = ref('00')
const clockSeconds = ref('00')
const currentTime = ref('')
const currentUtcTime = ref('')
let clockTimer = null

const daysEN = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const monthsEN = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const daysID = ['MIN', 'SEN', 'SEL', 'RAB', 'KAM', 'JUM', 'SAB']
const monthsID = ['JAN', 'FEB', 'MAR', 'APR', 'MEI', 'JUN', 'JUL', 'AGU', 'SEP', 'OKT', 'NOV', 'DES']

function updateClock() {
  const now = new Date()
  const isId = locale.value === 'id'
  const days = isId ? daysID : daysEN
  const months = isId ? monthsID : monthsEN
  clockDayStr.value = days[now.getDay()]
  clockDateStr.value = `${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`
  clockHours.value = String(now.getHours()).padStart(2, '0')
  clockMinutes.value = String(now.getMinutes()).padStart(2, '0')
  clockSeconds.value = String(now.getSeconds()).padStart(2, '0')
  currentTime.value = now.toLocaleTimeString()
  currentUtcTime.value = now.toUTCString()
}

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
})

const upCount = computed(() => props.servers.filter(s => s.is_online).length)
const downCount = computed(() => props.servers.filter(s => !s.is_online && s.last_seen).length)

const activeProblems = computed(() => props.problems.filter(p => p.is_active))

const dangerCount = computed(() => activeProblems.value.filter(p => p.severity === 'danger').length)
const avgCount = computed(() => activeProblems.value.filter(p => p.severity === 'average').length)
const warnCount = computed(() => activeProblems.value.filter(p => p.severity === 'warning').length)
const infoCount = computed(() => activeProblems.value.filter(p => !p.severity || p.severity === 'info').length)

const filteredServers = computed(() => {
  if (!fleetFilter.value) return props.servers
  const q = fleetFilter.value.toLowerCase()
  return props.servers.filter(s =>
    (s.hostname && s.hostname.toLowerCase().includes(q)) ||
    (s.ip_address && s.ip_address.toLowerCase().includes(q)) ||
    (s.group_name && s.group_name.toLowerCase().includes(q))
  )
})

function formatTime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return isoStr
  }
}

function calcDuration(startedAt) {
  if (!startedAt) return '0m'
  try {
    const start = new Date(startedAt).getTime()
    const diff = Math.max(0, Math.floor((Date.now() - start) / 1000))
    if (diff < 60) return `${diff}s`
    if (diff < 3600) return `${Math.floor(diff / 60)}m`
    return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
  } catch {
    return '-'
  }
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
</script>
