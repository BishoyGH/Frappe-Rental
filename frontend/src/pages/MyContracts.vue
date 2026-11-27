<template>
  <div class="mx-auto max-w-3xl px-4 py-6" data-testid="my-contracts">
    <div class="mb-4 flex items-center justify-between">
      <h1 class="text-xl font-semibold">{{ __('My contracts') }}</h1>
      <router-link :to="{ name: 'MyBookings' }" class="text-ink-blue-3 hover:underline">{{ __('My bookings') }}</router-link>
    </div>
    <div v-if="guest" class="rounded border p-4" data-testid="mc-login">
      <p class="mb-2">{{ __('Sign in to see your contracts.') }}</p>
      <a :href="loginUrl" class="text-ink-blue-3 hover:underline">{{ __('Sign in') }}</a>
    </div>
    <template v-else>
      <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700">{{ error }}</div>
      <p v-if="loaded && !rows.length" class="text-ink-gray-5" data-testid="mc-empty">{{ __('No contracts yet.') }}</p>
      <router-link v-for="r in rows" :key="r.name" :to="{ name: 'MyContractDetail', params: { name: r.name } }" class="mb-2 flex items-center justify-between rounded border p-3 hover:bg-surface-gray-1" data-testid="mc-row">
        <div>
          <div class="font-medium">{{ r.name }}</div>
          <div class="text-sm text-ink-gray-5">{{ fmtDate(r.start_date) }} → {{ r.open_ended ? __('open-ended') : fmtDate(r.end_date) }}</div>
        </div>
        <StatusBadge :status="r.status" />
      </router-link>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { boot } from '../boot'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const rows = ref([])
const loaded = ref(false)
const error = ref('')
const guest = computed(() => !boot.user || boot.user === 'Guest')
const loginUrl = computed(() => '/login?redirect-to=' + encodeURIComponent(window.location.pathname))

onMounted(async () => {
  if (guest.value) return
  try {
    rows.value = (await api('contract.my_contracts')).rows
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  } finally {
    loaded.value = true
  }
})
</script>
