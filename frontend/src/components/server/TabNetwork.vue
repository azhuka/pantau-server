<template>
  <div class="space-y-4">
    <!-- Network Interfaces Table -->
    <div class="noc-card p-3">
      <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-2">
        <span>🌐</span>
        <span>Antarmuka Jaringan & Lalu Lintas (Network Interfaces)</span>
      </h3>
      <div class="overflow-x-auto">
        <table class="w-full noc-table text-left">
          <thead>
            <tr>
              <th>Antarmuka</th>
              <th>Alamat IP</th>
              <th>Alamat MAC</th>
              <th>Kecepatan</th>
              <th>Status</th>
              <th>RX Total</th>
              <th>TX Total</th>
              <th>Laju Masuk (RX)</th>
              <th>Laju Keluar (TX)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="net in overview?.net || []" :key="net.iface">
              <td class="font-mono font-bold text-noc-cyan">{{ net.iface }}</td>
              <td class="font-mono text-xs text-noc-text">
                {{ (net.ip_addrs || []).join(', ') || '—' }}
              </td>
              <td class="font-mono text-[11px] text-noc-muted">{{ net.mac || '—' }}</td>
              <td class="font-mono text-[11px] text-noc-dim">{{ net.speed || '—' }}</td>
              <td>
                <span class="noc-badge" :class="net.is_up ? 'noc-badge-green' : 'noc-badge-gray'">
                  {{ net.is_up ? 'UP' : 'DOWN' }}
                </span>
              </td>
              <td class="font-mono text-xs">{{ formatBytes(net.rx) }}</td>
              <td class="font-mono text-xs">{{ formatBytes(net.tx) }}</td>
              <td class="font-mono text-xs text-emerald-400">{{ formatBitrate(net.rx_rate) }}</td>
              <td class="font-mono text-xs text-noc-cyan">{{ formatBitrate(net.tx_rate) }}</td>
            </tr>
            <tr v-if="!overview?.net || overview?.net.length === 0">
              <td colspan="9" class="text-center py-4 text-noc-muted">Belum ada telemetri antarmuka jaringan yang dilaporkan</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Listening Ports & Firewall Split -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <!-- Listening Ports -->
      <div class="noc-card p-3">
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim mb-2 flex items-center gap-1.5">
          <span>🔌</span>
          <span>Port Listening Aktif (Socket ss -tulpn)</span>
        </h3>
        <div class="overflow-x-auto max-h-72">
          <table class="w-full noc-table text-left">
            <thead>
              <tr>
                <th class="w-16">Proto</th>
                <th>Port</th>
                <th>Alamat Bind</th>
                <th>Proses / PID</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="port in listeningPorts" :key="`${port.proto}-${port.port}`">
                <td class="font-mono text-[11px] uppercase font-bold text-noc-cyan">{{ port.proto }}</td>
                <td class="font-mono text-xs font-bold text-noc-text">{{ port.port }}</td>
                <td class="font-mono text-xs text-noc-dim">{{ port.ip }}</td>
                <td class="font-mono text-[11px] text-noc-muted truncate max-w-[140px]">
                  {{ port.proc || port.pname }} {{ port.pid ? `(${port.pid})` : '' }}
                </td>
              </tr>
              <tr v-if="listeningPorts.length === 0">
                <td colspan="4" class="text-center py-4 text-noc-muted">Tidak ada socket listening yang terdeteksi</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Firewall Status -->
      <div class="noc-card p-3">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-bold uppercase tracking-wider text-noc-dim flex items-center gap-1.5">
            <span>🛡️</span>
            <span>Status Firewall (UFW / Iptables)</span>
          </h3>
          <span
            class="noc-badge uppercase font-bold"
            :class="firewall?.status === 'active' ? 'noc-badge-green' : 'noc-badge-gray'"
          >
            {{ firewall?.status || 'INACTIVE' }}
          </span>
        </div>

        <div class="space-y-2 text-xs">
          <div class="p-2.5 rounded bg-noc-bg border border-noc-border text-noc-muted font-mono text-[11px]">
            <div>Backend: <strong class="text-noc-text">{{ firewall?.backend || 'iptables/nftables' }}</strong></div>
            <div>Aturan Aktif: <strong class="text-noc-text">{{ (firewall?.rules || []).length }} baris</strong></div>
            <div>IP Terblokir: <strong class="text-rose-400 font-bold">{{ (firewall?.blocked_ips || []).length }} alamat</strong></div>
          </div>

          <div v-if="(firewall?.blocked_ips || []).length > 0" class="overflow-x-auto max-h-40">
            <table class="w-full noc-table text-left">
              <thead>
                <tr>
                  <th>Alamat IP Sumber Terblokir</th>
                  <th>Paket</th>
                  <th>Bytes</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in firewall.blocked_ips" :key="b.source">
                  <td class="font-mono text-rose-400 font-bold">{{ b.source }}</td>
                  <td class="font-mono text-noc-muted">{{ b.pkts }}</td>
                  <td class="font-mono text-noc-muted">{{ b.bytes }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  overview: Object,
})

const listeningPorts = computed(() => {
  return props.overview?.listening_ports || []
})

const firewall = computed(() => {
  return props.overview?.firewall || {}
})

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

function formatBitrate(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return '0 bps'
  const bits = bytesPerSec * 8
  const sizes = ['bps', 'Kbps', 'Mbps', 'Gbps']
  const i = Math.floor(Math.log(bits) / Math.log(1000))
  return `${(bits / Math.pow(1000, i)).toFixed(1)} ${sizes[i]}`
}
</script>
