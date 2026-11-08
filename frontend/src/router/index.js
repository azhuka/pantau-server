import { createRouter, createWebHistory } from 'vue-router';
import AppLayout from '@/components/AppLayout.vue';
import DashboardView from '@/views/DashboardView.vue';
import ServersView from '@/views/ServersView.vue';
import ProblemsView from '@/views/ProblemsView.vue';
import ProbingView from '@/views/ProbingView.vue';
import MaintenanceView from '@/views/MaintenanceView.vue';
import AuditView from '@/views/AuditView.vue';
import ProfileView from '@/views/ProfileView.vue';
import MasterControlView from '@/views/MasterControlView.vue';
import SettingsView from '@/views/SettingsView.vue';
import LogsView from '@/views/LogsView.vue';
import LoginView from '@/views/LoginView.vue';

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', name: 'dashboard', component: DashboardView },
      { path: 'servers', name: 'servers', component: ServersView },
      { path: 'problems', name: 'problems', component: ProblemsView },
      { path: 'probing', name: 'probing', component: ProbingView },
      { path: 'maintenance', name: 'maintenance', component: MaintenanceView },
      { path: 'audit', name: 'audit', component: AuditView },
      { path: 'profile', name: 'profile', component: ProfileView },
      { path: 'master-control', name: 'master-control', component: MasterControlView },
      { path: 'settings', name: 'settings', component: SettingsView },
      { path: 'logs', name: 'logs', component: LogsView },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
