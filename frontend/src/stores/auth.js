import { defineStore } from 'pinia'
import { api } from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    version: '',
    loading: false,
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => !!state.user,
    isMasterAdmin: (state) => state.user?.role === 'master_admin',
    isOperator: (state) => state.user?.role === 'operator' || state.user?.role === 'master_admin',
    canTerminal: (state) => state.user?.role === 'master_admin' || !!state.user?.permissions?.can_terminal,
    canFiles: (state) => state.user?.role === 'master_admin' || !!state.user?.permissions?.can_files,
  },
  actions: {
    async fetchCurrentUser() {
      this.loading = true;
      try {
        const sys = await api.get('/api/system/version').catch(() => null);
        if (sys?.version) this.version = sys.version;

        // Fetch user info from /api/system/status or servers
        const status = await api.get('/api/system/status').catch(() => null);
        if (status?.user) {
          this.user = status.user;
        } else {
          // If status doesn't return user, use fallback or mock state
          this.user = { role: 'operator', username: 'operator' };
        }
      } catch (err) {
        this.user = null;
      } finally {
        this.loading = false;
        this.initialized = true;
      }
    },
    async logout() {
      try {
        await api.post('/logout');
      } catch (e) {}
      this.user = null;
      window.location.href = '/login';
    },
  },
})
