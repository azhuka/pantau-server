import { defineStore } from 'pinia'
import { api } from '@/api/client'

export const useProblemStore = defineStore('problems', {
  state: () => ({
    problems: [],
    summary: {
      danger: 0,
      warning: 0,
      average: 0,
      info: 0,
      ignored: 0,
      total_active: 0,
    },
    loading: false,
    pollingInterval: null,
  }),
  actions: {
    async fetchProblems() {
      try {
        const data = await api.get('/api/problems');
        if (data) {
          this.problems = data.problems || [];
          this.summary = {
            danger: data.counts?.danger || 0,
            warning: data.counts?.warning || 0,
            average: data.counts?.average || 0,
            info: data.counts?.info || 0,
            ignored: data.counts?.ignored || 0,
            total_active: (data.counts?.danger || 0) + (data.counts?.warning || 0) + (data.counts?.average || 0),
          };
        }
      } catch (err) {
        console.error('Gagal mengambil data masalah:', err);
      }
    },
    async acknowledge(pid) {
      await api.post(`/api/alerts/${pid}/ack`);
      await this.fetchProblems();
    },
    async resolve(pid) {
      await api.post(`/api/alerts/${pid}/resolve`);
      await this.fetchProblems();
    },
    async ignore(pid, durationMins = 60) {
      await api.post(`/api/alerts/${pid}/ignore`, { duration: durationMins });
      await this.fetchProblems();
    },
    async unignore(pid) {
      await api.post(`/api/alerts/${pid}/unignore`);
      await this.fetchProblems();
    },
    startPolling(intervalMs = 6000) {
      this.stopPolling();
      this.fetchProblems();
      this.pollingInterval = setInterval(() => {
        if (!document.hidden) {
          this.fetchProblems();
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
