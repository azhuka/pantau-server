<template>
  <div class="space-y-3.5">
    <!-- 1. GLOBAL KPI BANNER (Asymmetric Grid: 210-240px + 1fr + 280-320px) -->
    <div class="dash-kpi-grid">
      <!-- KARTU 1: TOTAL SERVERS (Kompak 210px - 240px) -->
      <a
        href="#fleet"
        @click.prevent="$emit('nav', 'fleet')"
        id="kpi-card-total"
        class="bg-[#0c121e] border border-gray-800 border-l-[3px] border-l-[#38bdf8] p-3 px-4 rounded-lg flex flex-col justify-between hover:bg-[#111a2d] transition cursor-pointer select-none group shadow-md"
        :title="t('dash_open_fleet')"
      >
        <div class="flex items-center justify-between mb-1">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
            <span>{{ t('dash_kpi_total_servers') }}</span>
          </div>
          <span class="text-xs text-gray-500 group-hover:text-cyan-400 transition font-bold">→</span>
        </div>

        <div class="flex items-center justify-between gap-2">
          <div class="flex items-baseline gap-1.5 font-mono">
            <span class="text-3xl font-extrabold text-gray-100 leading-none">{{ servers.length }}</span>
            <span class="text-xs text-gray-400 font-medium">{{ t('dash_kpi_host') }}</span>
          </div>
          <div class="flex items-center gap-1.5 font-mono">
            <span class="px-2.5 py-1 rounded text-xs font-bold bg-emerald-950 text-emerald-400 border border-emerald-800" :title="t('online')">
              {{ upCount }} {{ t('dash_kpi_up') }}
            </span>
            <span
              class="px-2.5 py-1 rounded text-xs font-bold"
              :class="downCount > 0 ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-gray-800 text-gray-400 border border-gray-700'"
              :title="t('offline')"
            >
              {{ downCount }} {{ t('dash_kpi_down') }}
            </span>
          </div>
        </div>
      </a>

      <!-- KARTU 2: INSIDEN AKTIF DENGAN STRIP TINGKAT KEPARAHAN (1fr - Memanjang & Fleksibel) -->
      <div
        id="kpi-card-prob"
        class="bg-[#0c121e] border border-gray-800 border-l-[3px] p-3 px-4 rounded-lg flex flex-col justify-between shadow-md select-none"
        :class="dangerCount > 0 ? 'border-l-rose-500' : (avgCount > 0 ? 'border-l-orange-500' : (warnCount > 0 ? 'border-l-yellow-500' : 'border-l-emerald-500'))"
      >
        <div class="flex items-center justify-between mb-2">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
            <svg class="w-4 h-4" :class="dangerCount > 0 ? 'text-rose-400' : (warnCount > 0 ? 'text-amber-400' : 'text-emerald-400')" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>{{ t('dash_kpi_active_incidents') }}</span>
          </div>
          <div class="text-xs text-gray-400">
            {{ t('dash_kpi_total') }}: <strong class="text-gray-100 font-bold text-sm font-mono">{{ activeProblems.length }}</strong>
          </div>
        </div>

        <!-- Severity Tiles Strip (Zabbix Severity Strip 5 Kotak Terbaca Jelas & Proporsional) -->
        <div class="grid grid-cols-5 gap-2.5 text-center">
          <!-- Critical -->
          <div
            class="py-1.5 px-2 rounded-lg border transition cursor-pointer"
            :class="dangerCount > 0 ? 'bg-rose-950/80 border-rose-700 text-rose-300 font-bold' : 'bg-gray-900/60 border-gray-800 text-gray-500'"
            :title="t('sev_critical')"
          >
            <span class="text-base font-black leading-tight block font-mono">{{ dangerCount }}</span>
            <span class="text-xs uppercase font-bold block mt-1 tracking-wider">{{ t('sev_critical') }}</span>
          </div>

          <!-- High -->
          <div
            class="py-1.5 px-2 rounded-lg border transition cursor-pointer"
            :class="avgCount > 0 ? 'bg-orange-950/80 border-orange-700 text-orange-300 font-bold' : 'bg-gray-900/60 border-gray-800 text-gray-500'"
            :title="t('sev_high')"
          >
            <span class="text-base font-black leading-tight block font-mono">{{ avgCount }}</span>
            <span class="text-xs uppercase font-bold block mt-1 tracking-wider">{{ t('sev_high') }}</span>
          </div>

          <!-- Warning -->
          <div
            class="py-1.5 px-2 rounded-lg border transition cursor-pointer"
            :class="warnCount > 0 ? 'bg-amber-950/80 border-amber-700 text-amber-300 font-bold' : 'bg-gray-900/60 border-gray-800 text-gray-500'"
            :title="t('sev_warning')"
          >
            <span class="text-base font-black leading-tight block font-mono">{{ warnCount }}</span>
            <span class="text-xs uppercase font-bold block mt-1 tracking-wider">{{ t('sev_warning') }}</span>
          </div>

          <!-- Info -->
          <div
            class="py-1.5 px-2 rounded-lg border transition cursor-pointer"
            :class="infoCount > 0 ? 'bg-blue-950/80 border-blue-700 text-blue-300 font-bold' : 'bg-gray-900/60 border-gray-800 text-gray-500'"
            :title="t('sev_info')"
          >
            <span class="text-base font-black leading-tight block font-mono">{{ infoCount }}</span>
            <span class="text-xs uppercase font-bold block mt-1 tracking-wider">{{ t('sev_info') }}</span>
          </div>

          <!-- Ignored -->
          <div
            class="py-1.5 px-2 rounded-lg border bg-gray-900/60 border-gray-800 text-gray-500"
            :title="t('sev_ignored')"
          >
            <span class="text-base font-black leading-tight block font-mono">0</span>
            <span class="text-xs uppercase font-bold block mt-1 tracking-wider">{{ t('sev_ignored') }}</span>
          </div>
        </div>
      </div>

      <!-- KARTU 3: WAKTU SISTEM (Proporsional 280px - 320px) -->
      <div
        id="dashClockWidget"
        class="bg-[#0c121e] border border-gray-800 border-l-[3px] border-l-[#10b981] p-3 px-4 rounded-lg flex flex-col justify-between shadow-md select-none"
        :title="t('dash_kpi_system_clock')"
      >
        <div class="flex items-center justify-between mb-1">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 beacon-live"></span>
            <span>{{ t('dash_kpi_system_clock') }}</span>
          </div>
          <span class="text-xs px-2 py-0.5 rounded bg-gray-800 text-cyan-300 font-bold border border-gray-700">WIB</span>
        </div>

        <div class="flex items-center justify-between gap-3">
          <!-- Calendar: Day & Date -->
          <div class="flex flex-col">
            <span class="text-sm font-bold text-gray-100 leading-tight">{{ clockDayStr }}</span>
            <span class="text-xs text-gray-400 leading-tight mt-0.5">{{ clockDateStr }}</span>
          </div>

          <!-- Subtle Divider -->
          <div class="w-[1px] h-9 bg-gray-700/80" aria-hidden="true"></div>

          <!-- Digital Clock HH : MM : SS -->
          <div class="flex items-baseline text-2xl font-black text-cyan-400 tracking-wider font-mono">
            <span>{{ clockHours }}</span>
            <span class="text-cyan-500/70 animate-pulse mx-0.5">:</span>
            <span>{{ clockMinutes }}</span>
            <span class="text-cyan-500/70 animate-pulse mx-0.5">:</span>
            <span class="text-cyan-300 text-base font-bold">{{ clockSeconds }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. RECENT INCIDENTS CARD (MURNI PASIF) -->
    <div id="dash-problems-card" class="bg-[#0c121e] border border-gray-800 rounded-lg overflow-hidden shadow-md">
      <!-- Header Bar -->
      <div class="bg-[#0f172a] border-b border-gray-800 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2.5">
          <span
            class="w-5 h-5 rounded flex items-center justify-center text-xs font-black"
            :class="dangerCount > 0 ? 'bg-rose-500/20 text-rose-400' : (warnCount > 0 ? 'bg-amber-500/20 text-amber-400' : 'bg-emerald-500/20 text-emerald-400')"
          >
            {{ dangerCount > 0 ? '!' : (warnCount > 0 ? '!' : '✓') }}
          </span>
          <h3 class="text-sm font-bold text-gray-100 tracking-wide font-mono">
            {{ t('dash_recent_incidents') }}
          </h3>
          <span
            class="px-2.5 py-0.5 rounded text-xs font-mono font-bold"
            :class="activeProblems.length > 0 ? 'bg-rose-950 text-rose-300 border border-rose-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800'"
          >
            {{ activeProblems.length > 0 ? `${activeProblems.length} ${t('active_incidents')}` : t('nav_status_all_secure') }}
          </span>
        </div>

        <button
          @click="$emit('nav', 'fleet')"
          class="text-xs text-cyan-400 hover:text-cyan-300 transition font-mono flex items-center gap-1.5 cursor-pointer font-semibold"
        >
          <span>{{ t('dash_open_fleet') }}</span>
        </button>
      </div>

      <!-- State Kosong / 100% Normal -->
      <div
        v-if="activeProblems.length === 0"
        class="p-5 text-center text-xs text-gray-300 font-mono flex items-center justify-center gap-2.5 bg-[#090d16]/40 border-l-[3px] border-l-emerald-500"
      >
        <span class="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-bold">✓</span>
        <span>{{ t('dash_incidents_empty') }}</span>
      </div>

      <!-- Tabel Insiden Terkini -->
      <div v-else class="overflow-x-auto">
        <table class="w-full text-left text-sm font-mono border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-xs uppercase font-bold text-gray-400 bg-[#090d16]/80 select-none">
              <th class="py-2.5 px-4 w-28">{{ t('dash_col_time') }}</th>
              <th class="py-2.5 px-4 w-44">{{ t('dash_col_server') }}</th>
              <th class="py-2.5 px-3 w-32 text-center">{{ t('dash_col_severity') }}</th>
              <th class="py-2.5 px-4">{{ t('dash_col_description') }}</th>
              <th class="py-2.5 px-4 w-28 text-right">{{ t('dash_col_duration') }}</th>
              <th class="py-2.5 px-2 w-8 text-center"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#0c121e]/30">
            <tr
              v-for="prob in activeProblems"
              :key="prob.id"
              @click="$emit('inspect-node', prob.server_id)"
              class="hover:bg-blue-600/10 transition-colors cursor-pointer group"
              title="Click to inspect server in tactical workspace"
            >
              <!-- TIME -->
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap text-xs">
                {{ formatTime(prob.started_at) }}
              </td>

              <!-- SERVER -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2 font-bold text-gray-100 group-hover:text-cyan-400 transition text-sm">
                  <span class="w-2 h-2 rounded-full bg-blue-400"></span>
                  <span>{{ prob.hostname }}</span>
                </div>
              </td>

              <!-- SEVERITY -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="prob.severity === 'danger'"
                  class="px-2.5 py-1 rounded text-xs font-bold bg-rose-950 text-rose-300 border border-rose-800 uppercase"
                >
                  {{ t('sev_critical').toUpperCase() }}
                </span>
                <span
                  v-else-if="prob.severity === 'average'"
                  class="px-2.5 py-1 rounded text-xs font-bold bg-orange-950 text-orange-300 border border-orange-800 uppercase"
                >
                  {{ t('sev_high').toUpperCase() }}
                </span>
                <span
                  v-else-if="prob.severity === 'warning'"
                  class="px-2.5 py-1 rounded text-xs font-bold bg-amber-950 text-amber-300 border border-amber-800 uppercase"
                >
                  {{ t('sev_warning').toUpperCase() }}
                </span>
                <span
                  v-else
                  class="px-2.5 py-1 rounded text-xs font-bold bg-blue-950 text-blue-300 border border-blue-800 uppercase"
                >
                  {{ prob.severity || t('sev_info').toUpperCase() }}
                </span>
              </td>

              <!-- DESCRIPTION -->
              <td class="py-2.5 px-4 text-gray-100 font-medium text-sm leading-snug">
                <div>{{ prob.message }}</div>
                <div v-if="prob.tip" class="text-xs text-gray-400 font-normal mt-0.5 truncate max-w-xl">
                  {{ prob.tip }}
                </div>
              </td>

              <!-- DURATION -->
              <td class="py-2.5 px-4 text-right whitespace-nowrap text-gray-300 text-xs">
                <span class="px-2.5 py-0.5 rounded bg-gray-800 border border-gray-700 font-semibold font-mono">
                  {{ calcDuration(prob.started_at) }}
                </span>
              </td>

              <!-- NAVIGATION -->
              <td class="py-2.5 px-2 text-center text-gray-500 group-hover:text-cyan-400 transition font-bold text-base">
                ›
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. FLEET STATUS & PERFORMANCE CARD -->
    <div id="dash-fleet-card" class="bg-[#0c121e] border border-gray-800 rounded-lg overflow-hidden shadow-md">
      <!-- Toolbar -->
      <div class="bg-[#0f172a] border-b border-gray-800 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2.5">
          <span class="w-5 h-5 rounded bg-cyan-500/10 text-cyan-400 flex items-center justify-center text-xs">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
          </span>
          <div>
            <h3 class="text-sm font-bold text-gray-100">{{ t('dash_fleet_perf_title') }}</h3>
            <div class="text-xs text-gray-400">{{ t('dash_fleet_perf_sub') }}</div>
          </div>
        </div>

        <div class="flex items-center gap-2.5 font-mono">
          <!-- View Switcher (Tabel vs Grid) -->
          <div class="inline-flex bg-[#090d16] border border-gray-800 rounded-md p-0.5 text-xs">
            <button
              @click="fleetViewMode = 'table'"
              class="px-3 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="fleetViewMode === 'table' ? 'bg-blue-600/30 text-cyan-300 font-bold border border-blue-500/40' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_table')"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="9" x2="9" y2="21"/></svg>
              <span>{{ t('dash_view_table') }}</span>
            </button>
            <button
              @click="fleetViewMode = 'grid'"
              class="px-3 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="fleetViewMode === 'grid' ? 'bg-blue-600/30 text-cyan-300 font-bold border border-blue-500/40' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_grid')"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              <span>{{ t('dash_view_grid') }}</span>
            </button>
          </div>

          <!-- Search Filter -->
          <input
            v-model="fleetFilter"
            type="text"
            :placeholder="t('dash_search_host')"
            class="bg-[#090d16] border border-gray-800 focus:border-cyan-500 rounded px-3 py-1 text-xs text-gray-200 placeholder-gray-500 w-48 outline-none transition"
          />
        </div>
      </div>

      <!-- VIEW 1: TABEL OPERASIONAL REAL-TIME DASBOR -->
      <div v-if="fleetViewMode === 'table'" class="overflow-x-auto">
        <table class="w-full text-left text-sm border-collapse">
          <thead>
            <tr class="border-b border-gray-800 text-xs uppercase font-bold text-gray-400 bg-[#090d16]/80 select-none">
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
          <tbody class="divide-y divide-gray-800/40 bg-[#0c121e]/30">
            <tr
              v-for="s in filteredServers"
              :key="s.id"
              @click="$emit('inspect-node', s.id)"
              class="hover:bg-blue-600/10 transition-colors cursor-pointer group"
            >
              <!-- Server -->
              <td class="py-2.5 px-4 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="w-2.5 h-2.5 rounded-full" :class="s.is_online ? 'bg-emerald-400' : 'bg-rose-500'"></span>
                  <span class="font-bold text-gray-100 group-hover:text-cyan-400 transition text-sm">{{ s.hostname }}</span>
                  <span class="text-xs text-gray-400 font-normal">({{ s.group_name || 'Default' }})</span>
                </div>
              </td>

              <!-- Status -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  class="px-2.5 py-1 rounded text-xs font-bold font-mono"
                  :class="s.is_online ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'"
                >
                  {{ s.is_online ? t('online').toUpperCase() : t('offline').toUpperCase() }}
                </span>
              </td>

              <!-- Environment (Tier 1 / Tier 2) -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  class="px-2 py-0.5 rounded text-xs font-bold"
                  :class="s.tier === 1 ? 'bg-blue-950 text-blue-300 border border-blue-800' : 'bg-purple-950 text-purple-300 border border-purple-800'"
                >
                  {{ s.tier === 1 ? 'Tier 1' : 'Tier 2' }}
                </span>
              </td>

              <!-- Platform / IP -->
              <td class="py-2.5 px-4 whitespace-nowrap text-cyan-300 font-semibold font-mono text-sm">
                {{ s.ip_address }}
              </td>

              <!-- Uptime -->
              <td class="py-2.5 px-4 text-center whitespace-nowrap text-gray-300 text-xs font-mono">
                {{ formatUptime(s.uptime_secs) }}
              </td>

              <!-- CPU (%) -->
              <td class="py-2.5 px-4 text-center whitespace-nowrap text-sm font-mono">
                <span :class="s.cpu > 80 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ (s.cpu || 0).toFixed(1) }}%</span>
              </td>

              <!-- RAM (%) -->
              <td class="py-2.5 px-4 text-center whitespace-nowrap text-sm font-mono">
                <span :class="s.mem_pct > 80 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
              </td>

              <!-- Storage (%) -->
              <td class="py-2.5 px-4 text-center whitespace-nowrap text-sm font-mono">
                <span :class="(s.disk_pct || 35) > 85 ? 'text-rose-400 font-bold' : 'text-gray-200'">{{ s.disk_pct || 35 }}%</span>
              </td>

              <!-- Incidents -->
              <td class="py-2.5 px-3 text-center whitespace-nowrap">
                <span
                  v-if="s.active_problems_count > 0"
                  class="px-2.5 py-0.5 rounded text-xs font-bold font-mono bg-amber-950 text-amber-300 border border-amber-800"
                >
                  ● {{ s.active_problems_count }}
                </span>
                <span v-else class="text-gray-500 text-xs">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- VIEW 2: KARTU GRID DASBOR -->
      <div v-else class="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5 bg-[#090d16]/30">
        <div
          v-for="s in filteredServers"
          :key="s.id"
          @click="$emit('inspect-node', s.id)"
          class="bg-[#0c121e] border border-gray-800 hover:border-cyan-500/50 p-3.5 rounded-lg transition-all cursor-pointer group flex flex-col justify-between"
        >
          <div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 truncate">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" :class="s.is_online ? 'bg-emerald-400' : 'bg-rose-500'"></span>
                <span class="font-bold text-gray-100 text-sm truncate group-hover:text-cyan-400 transition">{{ s.hostname }}</span>
              </div>
              <span class="text-xs text-gray-400">{{ s.group_name }}</span>
            </div>
            <div class="text-xs text-cyan-400 font-mono mt-1.5 truncate font-semibold">{{ s.ip_address }}</div>
          </div>

          <div class="mt-3.5 space-y-2 text-xs">
            <div>
              <div class="flex items-center justify-between text-gray-400">
                <span class="font-medium">CPU</span>
                <span class="text-gray-200 font-bold font-mono">{{ (s.cpu || 0).toFixed(1) }}%</span>
              </div>
              <div class="w-full bg-gray-800 rounded-full h-1.5 mt-1 overflow-hidden">
                <div class="h-full bg-blue-500 rounded-full" :style="{ width: `${Math.min(s.cpu || 0, 100)}%` }"></div>
              </div>
            </div>

            <div>
              <div class="flex items-center justify-between text-gray-400">
                <span class="font-medium">RAM</span>
                <span class="text-gray-200 font-bold font-mono">{{ (s.mem_pct || 0).toFixed(1) }}%</span>
              </div>
              <div class="w-full bg-gray-800 rounded-full h-1.5 mt-1 overflow-hidden">
                <div class="h-full bg-emerald-500 rounded-full" :style="{ width: `${Math.min(s.mem_pct || 0, 100)}%` }"></div>
              </div>
            </div>
          </div>

          <div class="mt-2.5 pt-2 border-t border-gray-800/60 flex items-center justify-between text-xs font-mono text-gray-400">
            <span>Uptime: {{ formatUptime(s.uptime_secs) }}</span>
            <span v-if="s.active_problems_count > 0" class="text-amber-400 font-bold">● {{ s.active_problems_count }}</span>
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
let clockTimer = null

const daysEN = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const monthsEN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const daysID = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu']
const monthsID = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

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
