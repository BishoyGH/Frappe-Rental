<template>
  <div v-if="route.meta.public" class="min-h-screen w-full bg-surface-white text-ink-gray-9">
    <router-view />
  </div>
  <div v-else class="flex h-screen w-screen overflow-hidden bg-surface-white text-ink-gray-9">
    <AppSidebar />
    <main class="flex min-w-0 flex-1 flex-col">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'

const route = useRoute()
</script>
