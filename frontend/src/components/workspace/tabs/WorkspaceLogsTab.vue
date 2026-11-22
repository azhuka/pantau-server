<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
          // SYSTEM JOURNAL &amp; LOG STREAM
        </h3>
      </div>
      <span class="text-[11px] text-gray-400">JOURNALCTL -N 50</span>
    </div>
    <div class="bg-[#050811] border border-cyan-900/60 rounded-lg p-3 text-xs text-gray-300 font-mono max-h-[460px] overflow-y-auto space-y-1">
      <template v-if="(logsList || []).length > 0">
        <div v-for="(line, idx) in logsList" :key="idx" class="text-gray-300">
          {{ line }}
        </div>
      </template>
      <template v-else>
        <div class="text-gray-500">[2026-11-21 12:47:35] systemd[1]: Starting Pantau Monitoring Agent...</div>
        <div class="text-emerald-400">[2026-11-21 12:47:36] agent_pantau: Heartbeat dispatched successfully (200 OK).</div>
        <div class="text-gray-400">[2026-11-21 12:48:10] sshd[1090]: Accepted publickey for operator from 192.168.1.55 port 54102 ssh2</div>
      </template>
    </div>
  </div>
</template>

<script setup>
defineProps({
  logsList: { type: Array, default: () => [] }
})
</script>
