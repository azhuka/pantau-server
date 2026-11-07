<template>
  <div class="min-h-screen flex flex-col bg-noc-bg text-noc-text">
    <Navbar v-if="route.meta.layout !== 'empty'" />
    <main class="flex-1 max-w-[1720px] w-full mx-auto px-4 py-4">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Navbar from '@/components/layout/Navbar.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

onMounted(() => {
  authStore.fetchCurrentUser()
})
</script>
