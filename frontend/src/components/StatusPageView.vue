<template>
  <div class="space-y-5 font-mono max-w-5xl mx-auto">
    <div class="hud-tactical-card p-4 rounded-xl flex items-center justify-between gap-3 flex-wrap shadow-lg">
      <div>
        <h2 class="text-base font-extrabold text-cyan-300 tracking-wider uppercase">System Status Page</h2>
        <p class="text-xs text-gray-400 mt-0.5">Live availability summary across monitored infrastructure and synthetic endpoints.</p>
      </div>
      <span class="px-3 py-1 rounded text-xs font-bold uppercase border" :class="overallClass">
        {{ overallLabel }}
      </span>
    </div>

    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-gray-400">Total Assets</div><div class="text-2xl font-extrabold text-gray-100 mt-1">{{ counts.total_assets }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-emerald-400">Operational</div><div class="text-2xl font-extrabold text-emerald-300 mt-1">{{ counts.operational }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-amber-400">Degraded / Maint</div><div class="text-2xl font-extrabold text-amber-300 mt-1">{{ counts.degraded + counts.maintenance }}</div></div>
      <div class="hud-tactical-card p-3 rounded-xl"><div class="text-[11px] text-rose-400">Down</div><div class="text-2xl font-extrabold text-rose-300 mt-1">{{ counts.down }}</div></div>
    </div>

    <div class="hud-tactical-card rounded-xl p-4 space-y-3">
      <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider">Infrastructure Assets</h3>
      <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
        <div v-for="a in assets" :key="a.hostname" class="p-2.5 rounded-lg bg-[#070c18] border border-gray-800 flex items-center justify-between">
          <div>
            <div class="text-xs font-bold text-gray-100">{{ a.hostname }}</div>
            <div class="text-[10px] text-gray-500">{{ a.group }}</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border" :class="itemClass(a.status)">{{ a.status }}</span>
        </div>
      </div>
    </div>

    <div v-if="probes.length > 0" class="hud-tactical-card rounded-xl p-4 space-y-3">
      <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider">Synthetic Endpoints</h3>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <div v-for="p in probes" :key="p.name" class="p-2.5 rounded-lg bg-[#070c18] border border-gray-800 flex items-center justify-between">
          <div>
            <div class="text-xs font-bold text-gray-100">{{ p.name }}</div>
            <div class="text-[10px] text-gray-500 uppercase">{{ p.type }} · 24h Uptime {{ p.uptime_24h }}%</div>
          </div>
          <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase border" :class="itemClass(p.status)">{{ p.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const summary = ref({ overall_status: 'operational', counts: { total_assets: 0, operational: 0, degraded: 0, down: 0, maintenance: 0 }, assets: [], probes: [] })
const counts = computed(() => summary.value.counts || {})
const assets = computed(() => summary.value.assets || [])
const probes = computed(() => summary.value.probes || [])

const overallLabel = computed(() => (summary.value.overall_status || 'operational').replace('_', ' '))
const overallClass = computed(() => {
  const s = summary.value.overall_status
  if (s === 'operational') return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60'
  if (s === 'degraded' || s === 'partial_outage') return 'bg-amber-950/80 text-amber-300 border-amber-600/60'
  return 'bg-rose-950/80 text-rose-300 border-rose-600/60'
})

function itemClass(st) {
  if (st === 'operational' || st === 'up') return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60'
  if (st === 'degraded' || st === 'maintenance') return 'bg-amber-950/80 text-amber-300 border-amber-600/60'
  return 'bg-rose-950/80 text-rose-300 border-rose-600/60'
}

onMounted(async () => {
  const res = await fetch('/api/status-page/summary')
  if (res.ok) summary.value = await res.json()
})
</script>
