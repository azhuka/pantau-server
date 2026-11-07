import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: 'Dasbor Utama' },
  },
  {
    path: '/servers',
    name: 'Servers',
    component: () => import('@/views/ServersView.vue'),
    meta: { title: 'Daftar Server' },
  },
  {
    path: '/servers/:id',
    name: 'ServerDetail',
    component: () => import('@/views/ServerDetailView.vue'),
    meta: { title: 'Rincian & Kendali Server' },
  },
  {
    path: '/probing',
    name: 'Probing',
    component: () => import('@/views/ProbingView.vue'),
    meta: { title: 'Pemantauan Synthetic Probing' },
  },
  {
    path: '/maintenance',
    name: 'Maintenance',
    component: () => import('@/views/MaintenanceView.vue'),
    meta: { title: 'Jadwal Pemeliharaan' },
  },
  {
    path: '/logs',
    name: 'AuditLogs',
    component: () => import('@/views/AuditView.vue'),
    meta: { title: 'Catatan Audit & Jurnal' },
  },
  {
    path: '/master-control',
    name: 'MasterControl',
    component: () => import('@/views/MasterControlView.vue'),
    meta: { title: 'Pusat Kendali Master' },
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('@/views/UsersView.vue'),
    meta: { title: 'Manajemen Pengguna' },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { title: 'Profil & Keamanan' },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: 'Masuk Sistem', layout: 'empty' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title ? to.meta.title + ' — ' : ''}Pantau Server`;
  next();
})

export default router
