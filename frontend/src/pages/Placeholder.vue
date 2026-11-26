<template>
  <header class="flex items-center gap-2 border-b px-4 py-2.5">
    <span class="text-ink-gray-5">Rental /</span>
    <h1 class="text-base font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
  </header>
  <div class="grid flex-1 place-items-center p-8 text-center text-ink-gray-5">
    <p>{{ route.meta.title }} comes in a later release.</p>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>
