import { defineStore } from 'pinia'
import { api } from '@/api/client'

export const useServerStore = defineStore('servers', {
  state: () => ({
    servers: [],
    loading: false,
    filterStatus: 'all',
    searchQuery: '',
    activeServer: null,
    activeOverview: null,
    pollingInterval: null,
  }),
  getters: {
    filteredServers: (state) => {
      let list = state.servers;
      if (state.filterStatus !== 'all') {
        list = list.filter((s) => s.status === state.filterStatus);
      }
      if (state.searchQuery.trim()) {
        const q = state.searchQuery.toLowerCase();
        list = list.filter((s) =>
          (s.hostname && s.hostname.toLowerCase().includes(q)) ||
          (s.ip_address && s.ip_address.toLowerCase().includes(q))
        );
      }
      return list;
    },
    counts: (state) => {
      const counts = { total: state.servers.length, up: 0, down: 0, stale: 0, maintenance: 0 };
      for (const s of state.servers) {
        if (s.is_maintenance) counts.maintenance++;
        else if (s.status === 'up') counts.up++;
        else if (s.status === 'stale') counts.stale++;
        else counts.down++;
      }
      return counts;
    },
  },
  actions: {
    async fetchServers() {
      try {
        const data = await api.get('/api/servers');
        if (data && Array.isArray(data.servers)) {
          this.servers = data.servers;
        } else if (Array.isArray(data)) {
          this.servers = data;
        }
      } catch (err) {
        console.error('Gagal mengambil daftar server:', err);
      }
    },
    async fetchServerOverview(sid) {
      try {
        const data = await api.get(`/api/servers/${sid}/overview`);
        this.activeOverview = data;
        return data;
      } catch (err) {
        console.error(`Gagal mengambil overview server ${sid}:`, err);
        return null;
      }
    },
    startPolling(intervalMs = 5000) {
      this.stopPolling();
      this.fetchServers();
      this.pollingInterval = setInterval(() => {
        if (!document.hidden) {
          this.fetchServers();
        }
      }, intervalMs);
    },
    stopPolling() {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
    },
  },
})
