<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div style="text-align:center;margin-bottom:28px">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color:var(--blue);margin-bottom:8px">
          <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
          <path d="M2 17l10 5 10-5"></path>
          <path d="M2 12l10 5 10-5"></path>
        </svg>
        <h1 style="font-size:18px;font-weight:800;letter-spacing:1px;color:#fff;text-transform:uppercase;margin:0">PANTAU SERVER</h1>
        <div style="font-size:12px;color:var(--dim);margin-top:4px">DINAS KOMINFO STATISTIK DAN PERSANDIAN KAB. BARRU</div>
      </div>

      <form @submit.prevent="handleLogin" style="display:flex;flex-direction:column;gap:14px">
        <div v-if="errorMsg" class="badge badge-danger" style="padding:8px 12px;border-radius:6px;font-size:11.5px;text-transform:none">
          {{ errorMsg }}
        </div>

        <div class="filter-group">
          <label class="filter-label">Username</label>
          <input type="text" v-model="username" class="filter-input" required placeholder="Masukkan username" autofocus>
        </div>

        <div class="filter-group">
          <label class="filter-label">Kata Sandi</label>
          <input type="password" v-model="password" class="filter-input" required placeholder="Masukkan kata sandi">
        </div>

        <button type="submit" class="btn btn-primary" :disabled="loading" style="height:36px;margin-top:6px">
          {{ loading ? 'Memverifikasi...' : 'Masuk ke Sistem' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '@/api';

const router = useRouter();
const username = ref('');
const password = ref('');
const loading = ref(false);
const errorMsg = ref('');

async function handleLogin() {
  loading.value = true;
  errorMsg.value = '';
  try {
    const formData = new FormData();
    formData.append('username', username.value);
    formData.append('password', password.value);

    await api.post('/login', formData);
    router.push('/');
  } catch (e) {
    errorMsg.value = e.message || 'Username atau kata sandi tidak valid';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  width: 100%;
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 400px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 32px 28px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
}
</style>
