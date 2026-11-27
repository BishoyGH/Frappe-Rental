<template>
  <div class="mx-auto max-w-3xl px-4 py-6" data-testid="my-bookings">
    <div class="mb-4 flex items-center justify-between">
      <h1 class="text-xl font-semibold">{{ __('My bookings') }}</h1>
      <a href="/rentals" class="text-ink-blue-3 hover:underline">{{ __('Browse rentals') }}</a>
    </div>
    <div v-if="guest" class="rounded border p-4" data-testid="mb-login">
      <p class="mb-2">{{ __('Sign in to see your bookings.') }}</p>
      <a :href="loginUrl" class="text-ink-blue-3 hover:underline">{{ __('Sign in') }}</a>
    </div>
    <template v-else>
      <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="mb-error">{{ error }}</div>
      <p v-if="loaded && !rows.length" class="text-ink-gray-5" data-testid="mb-empty">{{ __('No bookings yet.') }}</p>
      <router-link
        v-for="r in rows"
        :key="r.name"
        :to="{ name: 'MyBookingDetail', params: { name: r.name } }"
        class="mb-2 flex items-center justify-between rounded border p-3 hover:bg-surface-gray-1"
        data-testid="mb-row"
      >
        <div>
          <div class="font-medium">{{ r.item_name || r.name }}</div>
          <div class="text-sm text-ink-gray-5">{{ r.name }} · {{ fmtDate(r.from_datetime, true) }} → {{ fmtDate(r.to_datetime, true) }}</div>
        </div>
        <div class="flex items-center gap-3">
          <span>{{ Number(r.grand_total).toFixed(2) }} {{ r.currency }}</span>
          <StatusBadge :status="r.status" />
        </div>
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
    rows.value = (await api('portal.listing')).rows
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Something went wrong')
  } finally {
    loaded.value = true
  }
})
</script>
