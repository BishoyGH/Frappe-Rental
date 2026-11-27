<template>
  <PageHeader :title="__('Dashboard')" />
  <div class="min-w-0 flex-1 overflow-auto px-4 py-3" data-testid="dashboard">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="dash-error">{{ error }}</div>
    <div v-if="kpis" class="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="dash-kpis">
      <div v-for="c in cards" :key="c.key" class="rounded border p-3">
        <div class="text-xs text-ink-gray-5">{{ c.label }}</div>
        <div class="text-xl font-semibold" :data-testid="`kpi-${c.key}`">{{ c.value }}</div>
      </div>
    </div>
    <div v-if="board" class="grid gap-3 md:grid-cols-2" data-testid="dash-board">
      <section v-for="col in columns" :key="col.key" class="rounded border">
        <h3 class="border-b px-3 py-2 font-medium">{{ col.label }} ({{ board[col.key].length }})</h3>
        <p v-if="!board[col.key].length" class="px-3 py-2 text-ink-gray-5">{{ __('Nothing here') }}</p>
        <ul class="divide-y">
          <li v-for="b in board[col.key]" :key="b.name" class="px-3 py-2">
            <router-link :to="`/bookings/${b.name}`" class="text-ink-blue-3 hover:underline">{{ b.name }}</router-link>
            <span class="ml-2 text-ink-gray-6">{{ b.customer }}</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { __ } from '../lib/translate'

const kpis = ref(null)
const board = ref(null)
const error = ref('')
const columns = [
  { key: 'arrivals', label: __('Arrivals today') },
  { key: 'departures', label: __('Departures today') },
  { key: 'in_house', label: __('In use') },
  { key: 'overdue', label: __('Overdue returns') },
]
const cards = computed(() => [
  { key: 'active', label: __('Active bookings'), value: kpis.value.active_bookings },
  { key: 'out', label: __('Checked out'), value: kpis.value.checked_out },
  { key: 'overdue', label: __('Overdue'), value: kpis.value.overdue_returns },
  { key: 'revenue', label: __('Revenue this month'), value: kpis.value.revenue_this_month },
])
onMounted(async () => {
  try {
    ;[kpis.value, board.value] = await Promise.all([api('dashboard.kpis'), api('dashboard.today')])
  } catch (e) {
    error.value = e.message
  }
})
</script>
