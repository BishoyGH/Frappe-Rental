<template>
  <header class="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
    <router-link v-if="parent" :to="parent.to" class="text-ink-gray-5 hover:text-ink-gray-7">
      {{ parent.label }} /
    </router-link>
    <span v-else class="text-ink-gray-5">{{ __('Rental') }} /</span>
    <h1 class="text-base font-semibold" data-testid="page-title">{{ title }}</h1>
    <slot name="title-extra" />
    <span class="flex-1" />
    <slot />
  </header>
</template>

<script setup>
defineProps({ title: String, parent: Object })
</script>
