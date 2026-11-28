<template>
  <div class="space-y-4">
    <!-- 1. GLOBAL TACTICAL KPI BANNER (Asymmetric Grid: 220-250px + 1fr + 280-320px) -->
    <div class="dash-kpi-grid">
      <!-- KARTU 1: ASSET STATUS (Kompak 220px - 250px) -->
      <a
        href="#assets"
        @click.prevent="$emit('nav', 'assets')"
        id="kpi-card-total"
        class="hud-tactical-card p-3.5 px-4 rounded-xl flex flex-col justify-between hover:border-cyan-400/50 transition cursor-pointer group shadow-lg"
        :title="t('dash_open_assets')"
      >
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>
        
        <div class="flex items-center justify-between mb-1.5">
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2 whitespace-nowrap">
            <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
              <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
              <line x1="6" y1="6" x2="6.01" y2="6"/>
              <line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
            <span>{{ t('dash_kpi_total_servers').toUpperCase() }}</span>
          </div>
          <svg class="w-3.5 h-3.5 text-gray-500 group-hover:text-cyan-400 transition shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
          </svg>
        </div>

        <div class="flex items-center justify-between gap-2 flex-wrap">
          <div class="flex items-baseline gap-1.5 font-mono shrink-0">
            <span class="text-2xl font-black text-gray-100 leading-none tracking-tight">{{ servers.length }}</span>
            <span class="text-[11px] text-cyan-400 font-bold uppercase tracking-wider">{{ t('dash_kpi_host') }}</span>
          </div>
          <div class="flex items-center gap-1.5 font-mono text-xs shrink-0 whitespace-nowrap">
            <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-bold whitespace-nowrap shrink-0 bg-emerald-950/80 text-emerald-300 border border-emerald-700/60" :title="t('online')">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 beacon-live shrink-0"></span>
              <span>{{ upCount }} {{ t('dash_kpi_up').toUpperCase() }}</span>
            </span>
            <span
              class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded font-bold whitespace-nowrap shrink-0"
              :class="downCount > 0 ? 'bg-rose-950/80 text-rose-300 border border-rose-700/70 radar-critical' : 'bg-gray-800/80 text-gray-400 border border-gray-700'"
              :title="t('offline')"
            >
              <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="downCount > 0 ? 'bg-rose-400 radar-critical' : 'bg-gray-500'"></span>
              <span>{{ downCount }} {{ t('dash_kpi_down').toUpperCase() }}</span>
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
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2 whitespace-nowrap">
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :class="incidentDotClass"
            ></span>
            <span>{{ t('dash_kpi_active_incidents').toUpperCase() }}</span>
          </div>
          <div class="text-xs text-gray-400 font-mono whitespace-nowrap">
            {{ t('dash_kpi_total') }}: <strong class="text-cyan-300 font-bold text-sm">{{ activeProblems.length }}</strong>
          </div>
        </div>

        <!-- Severity Tiles Strip (Glosarium Baku 5-Tingkat Terbaca Jelas & Proporsional) -->
        <div class="grid grid-cols-5 gap-2 text-center font-mono">
          <!-- Danger (Merah - Bahaya) -->
          <div
            @click="openSevModal('danger')"
            class="py-1.5 px-1.5 rounded border transition cursor-pointer hover:brightness-125 active:scale-95"
            :class="dangerCount > 0 ? 'bg-rose-950/90 border-rose-500 text-rose-300 font-bold shadow-[0_0_8px_rgba(244,63,94,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_danger')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ dangerCount }}</span>
            <span class="text-[9.5px] uppercase font-bold block mt-0.5 tracking-normal">{{ t('sev_danger') }}</span>
          </div>

          <!-- Critical (Oranye Pekat - Kritis) -->
          <div
            @click="openSevModal('critical')"
            class="py-1.5 px-1.5 rounded border transition cursor-pointer hover:brightness-125 active:scale-95"
            :class="criticalCount > 0 ? 'bg-orange-950/90 border-orange-500 text-orange-300 font-bold shadow-[0_0_8px_rgba(249,115,22,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_critical')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ criticalCount }}</span>
            <span class="text-[9.5px] uppercase font-bold block mt-0.5 tracking-normal">{{ t('sev_critical') }}</span>
          </div>

          <!-- Warning (Kuning - Peringatan) -->
          <div
            @click="openSevModal('warning')"
            class="py-1.5 px-1.5 rounded border transition cursor-pointer hover:brightness-125 active:scale-95"
            :class="warnCount > 0 ? 'bg-amber-950/90 border-amber-500 text-amber-300 font-bold shadow-[0_0_8px_rgba(245,158,11,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_warning')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ warnCount }}</span>
            <span class="text-[9.5px] uppercase font-bold block mt-0.5 tracking-normal">{{ t('sev_warning') }}</span>
          </div>

          <!-- Info (Biru/Cyan - Info) -->
          <div
            @click="openSevModal('info')"
            class="py-1.5 px-1.5 rounded border transition cursor-pointer hover:brightness-125 active:scale-95"
            :class="infoCount > 0 ? 'bg-cyan-950/90 border-cyan-500 text-cyan-300 font-bold shadow-[0_0_8px_rgba(56,189,248,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_info')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ infoCount }}</span>
            <span class="text-[9.5px] uppercase font-bold block mt-0.5 tracking-normal">{{ t('sev_info') }}</span>
          </div>

          <!-- Ignored (Abu-abu / Netral - Diabaikan) -->
          <div
            @click="openSevModal('ignored')"
            class="py-1 px-1 rounded border transition cursor-pointer hover:brightness-125 active:scale-95"
            :class="ignoredCount > 0 ? 'bg-slate-900/90 border-slate-500 text-slate-300 font-bold shadow-[0_0_8px_rgba(148,163,184,0.3)]' : 'bg-gray-900/40 border-gray-800/80 text-gray-500'"
            :title="t('sev_ignored')"
          >
            <span class="text-base font-extrabold leading-tight block">{{ ignoredCount }}</span>
            <span class="text-[9.5px] uppercase font-bold block mt-0.5 tracking-wider">{{ t('sev_ignored') }}</span>
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
          <div class="text-xs font-bold uppercase tracking-wider text-gray-400 font-mono flex items-center gap-2 whitespace-nowrap">
            <span class="w-2 h-2 rounded-full bg-emerald-400 beacon-live shrink-0"></span>
            <span>{{ t('dash_kpi_system_clock').toUpperCase() }}</span>
          </div>
          <span class="text-[10px] px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-300 font-mono font-bold border border-emerald-700/60 shrink-0">
            {{ t('dash_kpi_wita') }}
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
            class="w-2.5 h-2.5 rounded-full shrink-0"
            :class="incidentDotClass"
          ></span>
          <h3 class="text-xs font-bold text-gray-100 tracking-wider uppercase">
            {{ t('dash_recent_incidents') }}
          </h3>
          <span
            class="px-2 py-0.2 rounded text-[11px] font-bold"
            :class="incidentBadgeClass"
          >
            {{ activeProblems.length > 0 ? t('dash_recent_incidents_badge', { count: activeProblems.length }) : (servers.length === 0 ? t('nav_status_no_nodes') : t('nav_status_all_secure')) }}
          </span>
        </div>

        <button
          @click="$emit('nav', 'incidents')"
          class="text-xs text-cyan-400 hover:text-cyan-300 transition font-mono flex items-center gap-1.5 cursor-pointer font-semibold"
        >
          <span>{{ t('dash_full_history') }}</span>
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
          <svg v-if="servers.length > 0" class="w-2.5 h-2.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span v-else class="text-[10px] text-gray-400">○</span>
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
            <tr class="border-b border-cyan-500/20 text-gray-400 bg-[#070c18]/80 font-bold tracking-wider select-none">
              <th class="py-2 pl-4 pr-3 w-28">{{ t('dash_col_time') }}</th>
              <th class="py-2 px-3 w-48">{{ t('dash_col_server') }}</th>
              <th class="py-2 px-3 w-28 text-center">{{ t('dash_col_severity') }}</th>
              <th class="py-2 px-3">{{ t('dash_col_description') }}</th>
              <th class="py-2 px-3 w-28 text-right">{{ t('dash_col_duration') }}</th>
              <th class="py-2 pl-2 pr-4 w-9 text-center"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="prob in activeProblems"
              :key="prob.id"
              @click="openProblemDetail(prob)"
              class="hover:bg-cyan-950/30 transition-colors group cursor-pointer"
              :title="`Open details for ${prob.hostname}`"
            >
              <!-- TIME -->
              <td
                class="py-2 pl-4 pr-3 text-gray-400 whitespace-nowrap cursor-help hover:text-cyan-300 transition"
                :title="formatFullTime(prob.started_at)"
              >
                {{ formatIncidentTime(prob.started_at) }}
              </td>

              <!-- SERVER (Host + Group Badge) -->
              <td class="py-2 px-3 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :class="prob.severity === 'danger' ? 'bg-rose-400 radar-critical' : (prob.severity === 'critical' || prob.severity === 'average' ? 'bg-orange-400 radar-critical' : (prob.severity === 'warning' ? 'bg-amber-400 radar-warning' : 'bg-cyan-400'))"
                  ></span>
                  <span class="font-bold text-gray-100 group-hover:text-cyan-300 transition">{{ prob.hostname }}</span>
                  <span
                    v-if="prob.group_name"
                    class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-slate-800/80 text-slate-300 border border-slate-700/60 uppercase"
                  >
                    {{ prob.group_name }}
                  </span>
                </div>
              </td>

              <!-- SEVERITY -->
              <td class="py-2 px-2.5 text-center whitespace-nowrap">
                <div class="inline-flex flex-col items-center gap-1">
                  <span
                    v-if="prob.severity === 'danger'"
                    class="px-2 py-0.5 rounded text-[10.5px] font-bold bg-rose-950 text-rose-300 border border-rose-700/80 uppercase shadow-[0_0_6px_rgba(244,63,94,0.3)] radar-critical"
                  >
                    {{ t('sev_danger').toUpperCase() }}
                  </span>
                  <span
                    v-else-if="prob.severity === 'critical' || prob.severity === 'average'"
                    class="px-2 py-0.5 rounded text-[10.5px] font-bold bg-orange-950 text-orange-300 border border-orange-700/80 uppercase shadow-[0_0_6px_rgba(249,115,22,0.3)] radar-critical"
                  >
                    {{ t('sev_critical').toUpperCase() }}
                  </span>
                  <span
                    v-else-if="prob.severity === 'warning'"
                    class="px-2 py-0.5 rounded text-[10.5px] font-bold bg-amber-950 text-amber-300 border border-amber-700/80 uppercase shadow-[0_0_6px_rgba(245,158,11,0.3)] radar-warning"
                  >
                    {{ t('sev_warning').toUpperCase() }}
                  </span>
                  <span
                    v-else
                    class="px-2 py-0.5 rounded text-[10.5px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-700/80 uppercase"
                  >
                    {{ t('sev_info').toUpperCase() }}
                  </span>

                  <!-- Handled / Ignored Sub-badges (Blueprint Parity) -->
                  <div v-if="prob.acknowledged_by || prob.is_ignored" class="inline-flex items-center justify-center gap-1">
                    <span
                      v-if="prob.acknowledged_by"
                      class="text-[9px] px-1.5 py-0.2 rounded font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-0.5 shadow-sm"
                      :title="t('dash_acked_by', { user: prob.acknowledged_by })"
                    >
                      <svg class="w-2.5 h-2.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                      <span>{{ t('dash_badge_handled') }}</span>
                    </span>
                    <span
                      v-if="prob.is_ignored"
                      class="text-[9px] px-1.5 py-0.2 rounded font-bold bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1"
                      :title="prob.ignored_reason || t('sev_ignored')"
                    >
                      <svg class="w-2.5 h-2.5 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
                      <span>{{ t('sev_ignored') }}</span>
                    </span>
                  </div>
                </div>
              </td>

              <!-- DESCRIPTION (Single-Line Compact Ala Blueprint) -->
              <td class="py-2 px-3 text-gray-200 font-medium leading-snug whitespace-nowrap overflow-hidden text-ellipsis max-w-md xl:max-w-xl" :title="formatIncidentTip(prob, locale) || formatIncidentMessage(prob, locale)">
                <span>{{ formatIncidentMessage(prob, locale) }}</span>
              </td>

              <!-- DURATION -->
              <td class="py-2 px-3 text-right whitespace-nowrap text-gray-300">
                <span class="px-2 py-0.5 rounded bg-gray-900 border border-gray-700/80 font-bold text-[10.5px]">
                  {{ formatIncidentDuration(prob.started_at, locale) }}
                </span>
              </td>

              <!-- PASSIVE NAVIGATION CHEVRON -->
              <td class="py-2 pl-2 pr-4 text-center text-gray-500 group-hover:text-cyan-400 transition">
                <svg class="w-3.5 h-3.5 mx-auto opacity-40 group-hover:opacity-100 group-hover:translate-x-0.5 transition" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 3. ASSET STATUS & PERFORMANCE TABLE (10 Kolom Standar Lengkap) -->
    <div id="dash-assets-card" class="hud-tactical-card rounded-xl overflow-hidden shadow-lg mb-8">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Toolbar -->
      <div class="bg-[#0b1324] border-b border-cyan-500/20 px-4 py-2.5 flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-2.5 font-mono">
          <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
            <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
            <line x1="6" y1="6" x2="6.01" y2="6"/>
            <line x1="6" y1="18" x2="6.01" y2="18"/>
          </svg>
          <div>
            <h3 class="text-xs font-bold text-gray-100 tracking-wider uppercase">
              {{ t('dash_status_perf_title') }}
            </h3>
            <p class="text-[10px] text-gray-400 font-mono hidden sm:block">
              {{ t('dash_status_perf_sub') }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2.5 font-mono flex-wrap">
          <!-- View Switcher (Tabel vs Grid) -->
          <div class="inline-flex bg-[#060a14] border border-cyan-900/40 rounded p-0.5 text-xs">
            <button
              @click="assetViewMode = 'table'"
              class="px-2 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="assetViewMode === 'table' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_table')"
            >
              <span>{{ t('dash_view_table') }}</span>
            </button>
            <button
              @click="assetViewMode = 'grid'"
              class="px-2 py-1 rounded transition cursor-pointer flex items-center gap-1.5"
              :class="assetViewMode === 'grid' ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_view_grid')"
            >
              <span>{{ t('dash_view_grid') }}</span>
            </button>
          </div>

          <!-- Density Switcher (= Compact vs ≡ Standard) -->
          <div v-if="assetViewMode === 'table'" class="inline-flex bg-[#060a14] border border-cyan-900/40 rounded p-0.5 text-xs">
            <button
              @click="tableDensity = 'compact'"
              class="px-2 py-1 rounded transition cursor-pointer font-bold"
              :class="tableDensity === 'compact' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_density_compact')"
            >
              =
            </button>
            <button
              @click="tableDensity = 'standard'"
              class="px-2 py-1 rounded transition cursor-pointer font-bold"
              :class="tableDensity === 'standard' ? 'bg-cyan-950 text-cyan-300 border border-cyan-500/50' : 'text-gray-400 hover:text-white'"
              :title="t('dash_density_standard')"
            >
              ≡
            </button>
          </div>

          <!-- Wallboard Kiosk Mode Toggle -->
          <button
            type="button"
            @click="toggleKioskMode"
            class="px-2.5 py-1 rounded border border-cyan-900/50 bg-[#060a14] text-gray-300 hover:text-cyan-300 hover:border-cyan-500/50 text-xs transition cursor-pointer inline-flex items-center gap-1.5"
            title="Toggle NOC Wallboard Fullscreen"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
              <line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
            </svg>
            <span class="hidden sm:inline">Wallboard</span>
          </button>

          <!-- Group Filter Dropdown (Includes Ungrouped Option) -->
          <select
            v-model="selectedGroup"
            class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 rounded px-2.5 py-1 text-xs text-gray-200 outline-none transition cursor-pointer"
          >
            <option value="">{{ t('dash_all_groups') }}</option>
            <option v-for="grp in groupMeta.groups" :key="grp" :value="grp">
              {{ grp }} ({{ groupMeta.counts[grp] }})
            </option>
            <option v-if="groupMeta.ungroupedCount > 0" value="__none__">
              {{ t('flt_ungrouped') }} ({{ groupMeta.ungroupedCount }})
            </option>
          </select>

          <!-- Search Filter -->
          <input
            v-model="assetFilter"
            type="search"
            :placeholder="t('dash_search_placeholder')"
            class="bg-[#060a14] border border-cyan-900/50 focus:border-cyan-400 rounded px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 w-44 outline-none transition"
          />

          <!-- Passive Filter Reset Button -->
          <button
            v-if="selectedGroup || assetFilter.trim()"
            type="button"
            @click="selectedGroup = ''; assetFilter = ''"
            class="px-2 py-1 rounded bg-[#060a14] border border-amber-700/50 text-amber-300 hover:border-amber-400 text-[11px] font-mono font-bold transition cursor-pointer"
            title="Reset dashboard asset filter"
          >
            {{ t('flt_reset') }}
          </button>
        </div>
      </div>

      <!-- VIEW 1: TABEL OPERASIONAL REAL-TIME DASBOR (10 Kolom Baku) -->
      <div v-if="assetViewMode === 'table'" class="overflow-x-auto">
        <table class="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr class="border-b border-cyan-500/20 font-bold text-gray-400 bg-[#070c18]/80 select-none tracking-wider">
              <!-- 0. Server -->
              <th @click="setSort('hostname')" class="pl-4 pr-3 cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('col_server') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <!-- 1. Status -->
              <th class="px-3 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('col_status') }}
              </th>
              <!-- 2. Lingkungan -->
              <th class="px-3 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_env') }}
              </th>
              <!-- 3. Platform / IP -->
              <th class="px-3.5 whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_platform_ip') }}
              </th>
              <!-- 4. Uptime -->
              <th @click="setSort('uptime')" class="px-3.5 text-center cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('col_uptime') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <!-- 5. CPU (%) -->
              <th @click="setSort('cpu')" class="px-3.5 text-center cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_cpu') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <!-- 6. RAM (%) -->
              <th @click="setSort('ram')" class="px-3.5 text-center cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_ram') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <!-- 7. STORAGE (%) -->
              <th @click="setSort('storage')" class="px-3.5 text-center cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_storage') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
              <!-- 8. Services -->
              <th class="px-3 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_services') }}
              </th>
              <!-- 9. Insiden -->
              <th @click="setSort('incidents')" class="pl-3 pr-4 text-center cursor-pointer hover:text-cyan-300 transition whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ t('dash_col_incidents') }} <span class="text-[10px] text-gray-500">↕</span>
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40 bg-[#090e1c]/40">
            <tr
              v-for="s in filteredServers"
              :key="s.id"
              @click="$emit('inspect-node', s.id)"
              class="hover:bg-cyan-950/20 transition-colors cursor-pointer group"
            >
              <!-- 0. Server -->
              <td class="pl-4 pr-3 whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <div class="flex items-center gap-2">
                  <span
                    class="w-2 h-2 rounded-full shrink-0"
                    :class="!s.is_online ? 'bg-rose-500 radar-critical' : (s.is_maintenance ? 'bg-amber-400 animate-pulse' : (s.danger_count > 0 ? 'bg-rose-400 radar-critical' : (s.critical_count > 0 ? 'bg-orange-400 radar-critical' : (s.warning_count > 0 ? 'bg-amber-400 radar-warning' : 'bg-emerald-400 beacon-live'))))"
                  ></span>
                  <span class="font-bold text-gray-100 group-hover:text-cyan-300 transition text-sm">{{ s.hostname }}</span>
                </div>
              </td>

              <!-- 1. Status -->
              <td class="px-3 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <span
                  v-if="s.is_maintenance"
                  class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-300 border border-amber-600/60"
                  :title="s.maintenance_reason ? `${t('status_maint')}: ${s.maintenance_reason}` : t('tooltip_node_maint')"
                >
                  {{ t('status_maint').toUpperCase() }}
                </span>
                <span
                  v-else
                  class="px-2 py-0.5 rounded text-[10px] font-bold"
                  :class="s.is_online ? 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/60' : 'bg-rose-950/80 text-rose-300 border border-rose-700/60'"
                >
                  {{ s.is_online ? t('online').toUpperCase() : t('offline').toUpperCase() }}
                </span>
              </td>

              <!-- 2. Lingkungan (Produksi vs Non-produksi) -->
              <td class="px-3 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <span
                  v-if="s.tier === 1"
                  class="inline-flex items-center justify-center p-1 rounded bg-emerald-950/40 text-emerald-400 border border-emerald-700/50"
                  :title="t('env_prod')"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                    <polyline points="9 12 11 14 15 10"/>
                  </svg>
                </span>
                <span
                  v-else
                  class="inline-flex items-center justify-center p-1 rounded bg-slate-900/60 text-slate-400 border border-slate-700/50"
                  :title="t('env_non_prod')"
                >
                  <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"/>
                    <path d="M8.5 2h7"/>
                    <path d="M7 16h10"/>
                  </svg>
                </span>
              </td>

              <!-- 3. Platform / IP -->
              <td class="px-3.5 whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <div class="flex items-center gap-2">
                  <!-- Platform Badge -->
                  <span
                    v-if="s.platform_type === 'lxc'"
                    class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-cyan-950/80 text-cyan-300 border border-cyan-700/60 inline-flex items-center gap-1"
                    :title="`Platform: ${s.platform_label || 'LXC'}`"
                  >
                    <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                    <span>{{ s.platform_label || 'LXC' }}</span>
                  </span>
                  <span
                    v-else-if="s.platform_type === 'vm'"
                    class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-purple-950/80 text-purple-300 border border-purple-700/60 inline-flex items-center gap-1"
                    :title="`Platform: ${s.platform_label || 'VM'}`"
                  >
                    <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
                    <span>{{ s.platform_label || 'VM' }}</span>
                  </span>
                  <span
                    v-else
                    class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 inline-flex items-center gap-1"
                    :title="`Platform: ${s.platform_label || 'BAREMETAL'}`"
                  >
                    <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                    <span>{{ s.platform_label || 'BAREMETAL' }}</span>
                  </span>

                  <!-- IP Address + Copy Icon -->
                  <div class="flex items-center gap-1 group/ip">
                    <span class="text-xs text-gray-300 font-mono">{{ s.ip_address }}</span>
                    <button
                      type="button"
                      @click.stop="copyIp(s.ip_address, s.id, $event)"
                      class="text-gray-500 hover:text-cyan-400 transition p-0.5 rounded cursor-pointer"
                      :title="copiedHostId === s.id ? t('dash_copied_ip') : t('dash_click_to_copy')"
                    >
                      <svg v-if="copiedHostId === s.id" class="w-3 h-3 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                      <svg v-else class="w-3 h-3 opacity-60 group-hover/ip:opacity-100 transition" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                        <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </td>

              <!-- 4. Uptime -->
              <td class="px-3.5 text-center whitespace-nowrap text-gray-300 text-xs font-mono" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                {{ formatUptime(s.uptime_secs, locale) }}
              </td>

              <!-- 5. CPU (%) Visual 10-Segment LED Battery Gauge -->
              <td class="px-3.5 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <div class="inline-flex items-center justify-center gap-2">
                  <div class="meter-led-track" :title="`CPU: ${(s.cpu || 0).toFixed(1)}%`">
                    <span
                      v-for="i in 10"
                      :key="i"
                      class="meter-led-seg"
                      :class="i <= getMeterLitSegments(s.cpu) ? getMeterClass(s.cpu) : ''"
                    ></span>
                  </div>
                  <strong class="font-mono text-xs min-w-[42px] text-left" :style="{ color: getMeterColor(s.cpu) }">
                    {{ (s.cpu || 0).toFixed(1) }}%
                  </strong>
                </div>
              </td>

              <!-- 6. RAM (%) Visual 10-Segment LED Battery Gauge -->
              <td class="px-3.5 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <div class="inline-flex items-center justify-center gap-2">
                  <div class="meter-led-track" :title="`RAM: ${(s.mem_pct || 0).toFixed(1)}%`">
                    <span
                      v-for="i in 10"
                      :key="i"
                      class="meter-led-seg"
                      :class="i <= getMeterLitSegments(s.mem_pct) ? getMeterClass(s.mem_pct) : ''"
                    ></span>
                  </div>
                  <strong class="font-mono text-xs min-w-[42px] text-left" :style="{ color: getMeterColor(s.mem_pct) }">
                    {{ (s.mem_pct || 0).toFixed(1) }}%
                  </strong>
                </div>
              </td>

              <!-- 7. STORAGE (%) Visual 10-Segment LED Battery Gauge -->
              <td class="px-3.5 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <div class="inline-flex items-center justify-center gap-2">
                  <div class="meter-led-track" :title="`Storage: ${(s.disk_pct || 0).toFixed(1)}%`">
                    <span
                      v-for="i in 10"
                      :key="i"
                      class="meter-led-seg"
                      :class="i <= getMeterLitSegments(s.disk_pct) ? getMeterClass(s.disk_pct) : ''"
                    ></span>
                  </div>
                  <strong class="font-mono text-xs min-w-[42px] text-left" :style="{ color: getMeterColor(s.disk_pct) }">
                    {{ (s.disk_pct || 0).toFixed(1) }}%
                  </strong>
                </div>
              </td>

              <!-- 8. Services (tot_svcs / up_svcs) -->
              <td class="px-3 text-center whitespace-nowrap font-mono text-xs font-bold" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <span v-if="!s.is_online || !s.services_total" class="text-gray-500">-</span>
                <span v-else>
                  <span class="text-emerald-400">{{ s.services_total }}</span><span class="text-gray-500">/</span><span :class="s.services_up < s.services_total ? 'text-amber-400' : 'text-emerald-400'">{{ s.services_up }}</span>
                </span>
              </td>

              <!-- 9. Insiden -->
              <td class="pl-3 pr-4 text-center whitespace-nowrap" :class="tableDensity === 'compact' ? 'py-1.5' : 'py-2.5'">
                <span
                  v-if="!s.is_online"
                  class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/80 text-rose-300 border border-rose-700/60 uppercase"
                >
                  {{ t('offline').toUpperCase() }}
                </span>
                <span
                  v-else-if="(!s.active_problems_count || s.active_problems_count === 0) && (!s.ignored_count || s.ignored_count === 0)"
                  class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 uppercase"
                >
                  {{ t('status_clear').toUpperCase() }}
                </span>
                <div v-else class="inline-flex items-center justify-center gap-1 flex-wrap">
                  <span
                    v-if="s.danger_count > 0"
                    class="px-1.5 py-0.2 rounded text-[10.5px] font-bold bg-rose-950 text-rose-300 border border-rose-700 shadow-sm radar-critical"
                    :title="s.danger_msgs || t('sev_danger')"
                  >
                    {{ s.danger_count }}
                  </span>
                  <span
                    v-if="s.critical_count > 0"
                    class="px-1.5 py-0.2 rounded text-[10.5px] font-bold bg-orange-950 text-orange-300 border border-orange-700 shadow-sm radar-critical"
                    :title="s.critical_msgs || t('sev_critical')"
                  >
                    {{ s.critical_count }}
                  </span>
                  <span
                    v-if="s.warning_count > 0"
                    class="px-1.5 py-0.2 rounded text-[10.5px] font-bold bg-amber-950 text-amber-300 border border-amber-700 shadow-sm radar-warning"
                    :title="s.warning_msgs || t('sev_warning')"
                  >
                    {{ s.warning_count }}
                  </span>
                  <span
                    v-if="s.info_count > 0"
                    class="px-1.5 py-0.2 rounded text-[10.5px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-700 shadow-sm"
                    :title="s.info_msgs || t('sev_info')"
                  >
                    {{ s.info_count }}
                  </span>
                  <span
                    v-if="s.ignored_count > 0"
                    class="px-1.5 py-0.2 rounded text-[10.5px] font-bold bg-slate-900 text-slate-400 border border-slate-700 shadow-sm"
                    :title="s.ignored_msgs || t('sev_ignored')"
                  >
                    {{ s.ignored_count }}
                  </span>
                </div>
              </td>
            </tr>

            <!-- Empty State Baris -->
            <tr v-if="filteredServers.length === 0">
              <td colspan="10" class="py-12 px-4 text-center text-gray-400 font-mono text-xs">
                <div class="flex flex-col items-center justify-center gap-1.5">
                  <svg class="w-8 h-8 text-gray-600 mb-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
                    <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
                    <line x1="6" y1="6" x2="6.01" y2="6"/>
                    <line x1="6" y1="18" x2="6.01" y2="18"/>
                  </svg>
                  <div class="font-bold text-gray-200">{{ t('assets_empty_title') }}</div>
                  <div class="text-gray-400 max-w-sm">{{ t('dash_assets_empty') }}</div>
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
            <svg class="w-8 h-8 text-gray-600 mb-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect width="20" height="8" x="2" y="2" rx="2" ry="2"/>
              <rect width="20" height="8" x="2" y="14" rx="2" ry="2"/>
              <line x1="6" y1="6" x2="6.01" y2="6"/>
              <line x1="6" y1="18" x2="6.01" y2="18"/>
            </svg>
            <div class="font-bold text-gray-200">{{ t('assets_empty_title') }}</div>
            <div class="text-gray-400 max-w-sm">{{ t('dash_assets_empty') }}</div>
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
                <span class="w-2 h-2 rounded-full shrink-0" :class="!s.is_online ? 'bg-rose-500 radar-critical' : (s.is_maintenance ? 'bg-amber-400 animate-pulse' : (s.danger_count > 0 ? 'bg-rose-400 radar-critical' : (s.critical_count > 0 ? 'bg-orange-400 radar-critical' : (s.warning_count > 0 ? 'bg-amber-400 radar-warning' : 'bg-emerald-400 beacon-live'))))"></span>
                <span class="font-bold text-gray-100 text-sm truncate group-hover:text-cyan-300 transition font-mono">{{ s.hostname }}</span>
              </div>
              <span class="text-[10px] font-mono text-gray-500 uppercase">{{ s.group_name || t('flt_ungrouped') }}</span>
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
            <span>UP // {{ formatUptime(s.uptime_secs, locale) }}</span>
            <div v-if="s.active_problems_count > 0" class="inline-flex items-center gap-1">
              <span v-if="s.danger_count > 0" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-700 radar-critical" :title="s.danger_msgs">{{ s.danger_count }}</span>
              <span v-if="s.critical_count > 0" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-orange-950 text-orange-300 border border-orange-700 radar-critical" :title="s.critical_msgs">{{ s.critical_count }}</span>
              <span v-if="s.warning_count > 0" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-700 radar-warning" :title="s.warning_msgs">{{ s.warning_count }}</span>
              <span v-if="s.info_count > 0" class="px-1.5 py-0.2 rounded text-[10px] font-bold bg-sky-950 text-sky-300 border border-sky-700" :title="s.info_msgs">{{ s.info_count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- SEVERITY DETAIL MODAL -->
    <SevDetailModal
      :is-open="showSevModal"
      :severity="activeSev"
      :problems="problems"
      :current-user="currentUser"
      @close="showSevModal = false"
      @open-problem-detail="openProblemDetail"
      @open-server="openHostFromModal"
      @unignore-problem="unignoreProblem"
      @ignore-problem="openIgnoreDialog"
      @ack-problem="handleProblemAck"
    />

    <!-- PROBLEM DETAIL & DIAGNOSTICS MODAL -->
    <ProblemDetailModal
      :is-open="showProblemDetailModal"
      :problem="selectedProblem"
      :current-user="currentUser"
      @close="showProblemDetailModal = false"
      @open-server="openHostFromModal"
      @ignore-problem="openIgnoreDialog"
      @terminate-ssh="terminateSshSession"
      @ack-problem="handleProblemAck"
    />

    <!-- IGNORE PROBLEM MODAL -->
    <IgnoreProblemModal
      :is-open="showIgnoreModal"
      :problem="problemToIgnore"
      :current-user="currentUser"
      @close="showIgnoreModal = false"
      @ignored="handleIgnored"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import {
  formatIncidentMessage,
  formatIncidentTip,
  formatIncidentTime,
  formatIncidentDuration,
  formatUptime,
  getMeterLitSegments,
  getMeterClass,
  getMeterColor
} from '../../utils/formatters'
import SevDetailModal from './SevDetailModal.vue'
import ProblemDetailModal from './ProblemDetailModal.vue'
import IgnoreProblemModal from './IgnoreProblemModal.vue'
import { extractGroupOptions, matchesGroupFilter, buildAssetSearchHaystack } from '../../utils/filterHelpers'
import { useToast, confirmAction } from '../../utils/useToast'

const toast = useToast()

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  },
  problems: {
    type: Array,
    default: () => []
  },
  currentUser: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['inspect-node', 'nav', 'refresh-problems'])

const { t, locale } = useI18n()

const showSevModal = ref(false)
const activeSev = ref('danger')

const showProblemDetailModal = ref(false)
const selectedProblem = ref(null)

const showIgnoreModal = ref(false)
const problemToIgnore = ref(null)

const copiedHostId = ref(null)
async function copyIp(ip, id, e) {
  if (e) e.stopPropagation()
  if (!ip) return
  try {
    await navigator.clipboard.writeText(ip)
    copiedHostId.value = id
    setTimeout(() => {
      if (copiedHostId.value === id) {
        copiedHostId.value = null
      }
    }, 1500)
  } catch (err) {
    console.error('Failed to copy IP:', err)
  }
}

function openSevModal(sev) {
  activeSev.value = sev
  showSevModal.value = true
}

function openProblemDetail(p) {
  selectedProblem.value = p
  showProblemDetailModal.value = true
}

function openIgnoreDialog(p) {
  problemToIgnore.value = p
  showIgnoreModal.value = true
}

async function handleProblemAck(pid) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${pid}/ack`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      }
    })
    const data = await res.json()
    if (data.ok) {
      if (selectedProblem.value && selectedProblem.value.id === pid) {
        selectedProblem.value.acknowledged_by = data.acknowledged_by
        selectedProblem.value.acknowledged_at = data.acknowledged_at
      }
      emit('refresh-problems')
    } else {
      toast.error(data.detail || 'Failed to acknowledge incident')
    }
  } catch (err) {
    console.error('Failed to acknowledge problem:', err)
  }
}



async function unignoreProblem(pid) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${pid}/unignore`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      emit('refresh-problems')
    } else {
      toast.error(data.detail || 'Failed to unignore incident')
    }
  } catch (err) {
    console.error('Failed to unignore problem:', err)
  }
}

async function terminateSshSession(prob) {
  const ok = await confirmAction({
    title: 'Terminate SSH Session',
    message: 'Force-terminate this active SSH session now?',
    confirmText: 'Terminate',
    variant: 'danger',
  })
  if (!ok) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/problems/${prob.id}/terminate-ssh`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      toast.success(data.message || 'SSH session termination signal sent.')
      showProblemDetailModal.value = false
      emit('refresh-problems')
    } else {
      toast.error(data.detail || 'Failed to terminate SSH session.')
    }
  } catch (err) {
    console.error('Failed to terminate SSH session:', err)
  }
}

function handleIgnored(payload) {
  if (selectedProblem.value && payload && selectedProblem.value.id === payload.id) {
    selectedProblem.value = {
      ...selectedProblem.value,
      is_ignored: true,
      ignored_until: payload.ignored_until || null,
      ignored_reason: payload.ignored_reason || null,
    }
  }
  emit('refresh-problems')
}

function openHostFromModal(sid) {
  showSevModal.value = false
  showProblemDetailModal.value = false
  if (props.servers && props.servers.length > 0) {
    const exists = props.servers.some(s => s.id === sid)
    if (!exists) {
      toast.error(t('access_denied_node') || 'Access denied: You do not have permission for this asset.')
      return
    }
  }
  emit('inspect-node', sid)
}

const assetViewMode = ref('table') // 'table' or 'grid'
const tableDensity = ref('standard') // 'standard' or 'compact'
const selectedGroup = ref('')
const assetFilter = ref('')

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

const groupMeta = computed(() => extractGroupOptions(props.servers))

// Clock state
const clockDayStr = ref('')
const clockDateStr = ref('')
const clockHours = ref('00')
const clockMinutes = ref('00')
const clockSeconds = ref('00')

function toggleKioskMode() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.().catch(() => {})
  } else {
    document.exitFullscreen?.().catch(() => {})
  }
}
const currentTime = ref('')
const currentUtcTime = ref('')
let clockTimer = null

const daysEN = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const monthsEN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const daysID = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu']
const monthsID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

function updateClock() {
  const now = new Date()
  const isId = locale.value === 'id'

  // Presisi zona waktu WITA (Asia/Makassar, UTC+8) di browser mana pun
  const witaFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Makassar',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })

  const parts = witaFormatter.formatToParts(now)
  const pMap = {}
  for (const p of parts) {
    pMap[p.type] = p.value
  }

  const dayFormatter = new Intl.DateTimeFormat(isId ? 'id-ID' : 'en-US', {
    timeZone: 'Asia/Makassar',
    weekday: 'long'
  })
  const monthFormatter = new Intl.DateTimeFormat(isId ? 'id-ID' : 'en-US', {
    timeZone: 'Asia/Makassar',
    month: 'long'
  })

  clockDayStr.value = dayFormatter.format(now)
  clockDateStr.value = `${pMap.day} ${monthFormatter.format(now)} ${pMap.year}`
  clockHours.value = pMap.hour || '00'
  clockMinutes.value = pMap.minute || '00'
  clockSeconds.value = pMap.second || '00'
  currentTime.value = `${clockHours.value}:${clockMinutes.value}:${clockSeconds.value} WITA`
  currentUtcTime.value = now.toUTCString()
}

function handleKeyDown(e) {
  if (e.key === 'Escape') {
    if (showIgnoreModal.value) {
      showIgnoreModal.value = false
    } else if (showProblemDetailModal.value) {
      showProblemDetailModal.value = false
    } else if (showSevModal.value) {
      showSevModal.value = false
    }
  }
}

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  window.addEventListener('keydown', handleKeyDown)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  window.removeEventListener('keydown', handleKeyDown)
})

const upCount = computed(() => props.servers.filter(s => s.is_online).length)
const downCount = computed(() => props.servers.filter(s => !s.is_online && s.last_seen).length)

const activeProblems = computed(() => props.problems.filter(p => p.is_active && !p.is_ignored))

const dangerCount = computed(() => activeProblems.value.filter(p => p.severity === 'danger').length)
const criticalCount = computed(() => activeProblems.value.filter(p => p.severity === 'critical' || p.severity === 'average').length)
const warnCount = computed(() => activeProblems.value.filter(p => p.severity === 'warning').length)
const infoCount = computed(() => activeProblems.value.filter(p => !p.severity || p.severity === 'info').length)
const ignoredCount = computed(() => props.problems.filter(p => p.is_ignored).length)

const incidentDotClass = computed(() => {
  if (dangerCount.value > 0) return 'bg-rose-400 radar-critical'
  if (criticalCount.value > 0) return 'bg-orange-400 radar-critical'
  if (warnCount.value > 0) return 'bg-amber-400 radar-warning'
  if (infoCount.value > 0) return 'bg-cyan-400'
  return 'bg-emerald-400 beacon-live'
})

const incidentBadgeClass = computed(() => {
  if (activeProblems.value.length === 0) {
    return props.servers.length === 0
      ? 'bg-gray-800/80 text-gray-400 border border-gray-700'
      : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
  }
  if (dangerCount.value > 0) return 'bg-rose-950/80 text-rose-300 border border-rose-800 shadow-[0_0_6px_rgba(244,63,94,0.3)] radar-critical'
  if (criticalCount.value > 0) return 'bg-orange-950/80 text-orange-300 border border-orange-800 shadow-[0_0_6px_rgba(249,115,22,0.3)] radar-critical'
  if (warnCount.value > 0) return 'bg-amber-950/80 text-amber-300 border border-amber-800 shadow-[0_0_6px_rgba(245,158,11,0.3)] radar-warning'
  if (infoCount.value > 0) return 'bg-cyan-950/80 text-cyan-300 border border-cyan-800 shadow-[0_0_6px_rgba(56,189,248,0.3)]'
  return 'bg-slate-900/80 text-slate-400 border border-slate-700'
})

const filteredServers = computed(() => {
  let list = props.servers || []
  if (selectedGroup.value) {
    list = list.filter(s => matchesGroupFilter(s.group_name, selectedGroup.value))
  }
  if (assetFilter.value.trim()) {
    const q = assetFilter.value.toLowerCase().trim()
    list = list.filter(s => buildAssetSearchHaystack(s).includes(q))
  }
  return [...list].sort((a, b) => {
    let aVal, bVal
    if (sortCol.value === 'hostname') {
      aVal = (a.hostname || '').toLowerCase()
      bVal = (b.hostname || '').toLowerCase()
    } else if (sortCol.value === 'uptime') {
      aVal = a.uptime_secs || 0
      bVal = b.uptime_secs || 0
    } else if (sortCol.value === 'cpu') {
      aVal = a.cpu || 0
      bVal = b.cpu || 0
    } else if (sortCol.value === 'ram') {
      aVal = a.mem_pct || 0
      bVal = b.mem_pct || 0
    } else if (sortCol.value === 'storage') {
      aVal = a.disk_pct || 0
      bVal = b.disk_pct || 0
    } else if (sortCol.value === 'incidents') {
      aVal = a.active_problems_count || 0
      bVal = b.active_problems_count || 0
    } else {
      aVal = a.id || 0
      bVal = b.id || 0
    }
    if (aVal < bVal) return sortAsc.value ? -1 : 1
    if (aVal > bVal) return sortAsc.value ? 1 : -1
    return 0
  })
})

function formatFullTime(isoStr) {
  if (!isoStr) return '-'
  try {
    const d = new Date(isoStr)
    return d.toLocaleString()
  } catch {
    return isoStr
  }
}
</script>

<style scoped>
/* 10-Segment LED Battery Gauge (Zabbix-Style) */
.meter-led-track {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 68px;
  height: 12px;
  padding: 2px;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 4px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.6);
  gap: 2px;
  box-sizing: border-box;
  vertical-align: middle;
  flex-shrink: 0;
}
.meter-led-seg {
  flex: 1;
  height: 100%;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.08);
  transition: background-color 0.2s ease, box-shadow 0.2s ease;
}
.meter-led-seg.on-green {
  background: linear-gradient(180deg, #34d399 0%, #10b981 100%);
  box-shadow: 0 0 2px rgba(16, 185, 129, 0.5);
}
.meter-led-seg.on-yellow {
  background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%);
  box-shadow: 0 0 2px rgba(245, 158, 11, 0.5);
}
.meter-led-seg.on-orange {
  background: linear-gradient(180deg, #fb923c 0%, #ea580c 100%);
  box-shadow: 0 0 2px rgba(249, 115, 22, 0.5);
}
.meter-led-seg.on-red {
  background: linear-gradient(180deg, #f87171 0%, #ef4444 100%);
  box-shadow: 0 0 3px rgba(239, 68, 68, 0.6);
}
</style>
