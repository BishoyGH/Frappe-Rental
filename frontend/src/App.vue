<template>
  <div class="flex h-screen w-screen overflow-hidden bg-surface-white text-ink-gray-9">
    <AppSidebar />
    <main class="flex min-w-0 flex-1 flex-col">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import AppSidebar from './components/AppSidebar.vue'
</script>
