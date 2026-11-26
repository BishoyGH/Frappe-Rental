<template>
  <PageHeader :title="__('Availability')" />

  <form class="flex flex-wrap items-end gap-2 border-b px-4 py-2" data-testid="av-form" @submit.prevent="search">
    <FormControl v-model="q.rental_type" type="select" :label="__('Type')" :options="opt(options.rental_types, __('All types'))" class="w-40" data-testid="av-type" />
    <FormControl v-model="q.from" type="datetime-local" :label="__('From')" data-testid="av-from" />
    <FormControl v-model="q.to" type="datetime-local" :label="__('To')" data-testid="av-to" />
    <FormControl v-model="q.location" type="select" :label="__('Location')" :options="opt(options.locations, __('Any'))" class="w-40" />
    <FormControl v-model="q.qty" type="number" :label="__('Qty')" min="1" class="w-20" />
    <Button type="submit" variant="solid" :label="__('Search')" :loading="loading" data-testid="av-search">
      <template #prefix><LucideSearch class="h-4 w-4" /></template>
    </Button>
  </form>

  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700">{{ error }}</div>
    <div v-if="message" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="av-message">{{ message }}</div>
    <table v-if="results" class="w-full min-w-[640px] border-collapse" data-testid="av-results">
      <thead>
        <tr>
          <th :class="th">{{ __('Item') }}</th>
          <th :class="th">{{ __('Unit') }}</th>
          <th :class="th">{{ __('Type') }}</th>
          <th :class="th">{{ __('Location') }}</th>
          <th :class="th">{{ __('Availability') }}</th>
          <th :class="[th, 'text-right']">{{ __('Price') }}</th>
          <th :class="th" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in results" :key="r.rental_unit" data-testid="av-row">
          <td :class="td"><span class="font-medium text-ink-gray-9">{{ r.item_name }}</span></td>
          <td :class="td">{{ r.unit_name }}</td>
          <td :class="td">{{ r.rental_type }}</td>
          <td :class="td">{{ r.location || '-' }}</td>
          <td :class="td"><Badge :label="__('Free')" theme="green" /></td>
          <td :class="[td, 'text-right tabular-nums']">{{ r.price == null ? '-' : `${fmtMoney(r.price)} ${r.currency}` }}</td>
          <td :class="[td, 'text-right']"><Button variant="solid" :label="__('Book')" data-testid="av-book" @click="book(r)" /></td>
        </tr>
        <tr v-if="!results.length">
          <td colspan="7" class="py-10 text-center text-ink-gray-5" data-testid="av-empty">{{ __('Nothing is free for that period.') }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="py-10 text-center text-ink-gray-5">{{ __('Pick dates and search to see free units with their price.') }}</p>
  </div>

  <QuickBook
    v-if="quick"
    v-bind="quick"
    @close="quick = null"
    @booked="booked"
  />
</template>

<script setup>
import { Badge, Button, FormControl } from 'frappe-ui'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import LucideSearch from '~icons/lucide/search'
import PageHeader from '../components/PageHeader.vue'
import QuickBook from '../components/QuickBook.vue'
import { api } from '../lib/api'
import { addDays, fmtMoney, fromInput, parseDt, startOfDay, toInput } from '../lib/format'
import { __ } from '../lib/translate'

const router = useRouter()
const th = 'whitespace-nowrap bg-surface-gray-1 px-2.5 py-1.5 text-left text-sm font-medium text-ink-gray-5'
const td = 'whitespace-nowrap border-b px-2.5 py-2 text-ink-gray-7'
const tomorrow = addDays(startOfDay(new Date()), 1)
tomorrow.setHours(9)
const q = reactive({ rental_type: '', location: '', qty: 1, from: toInput(tomorrow), to: toInput(addDays(tomorrow, 2)) })
const options = reactive({ rental_types: [], locations: [] })
const opt = (values, placeholder) => [{ label: placeholder, value: '' }, ...values.map((v) => ({ label: v, value: v }))]
const results = ref(null)
const loading = ref(false)
const error = ref('')
const message = ref('')
const quick = ref(null)

async function search() {
  loading.value = true
  error.value = ''
  try {
    results.value = await api('availability.search', {
      from_datetime: fromInput(q.from),
      to_datetime: fromInput(q.to),
      rental_type: q.rental_type || undefined,
      location: q.location || undefined,
      qty: q.qty || 1,
      limit: 200,
    })
  } catch (e) {
    error.value = e.messages?.[0] || __('Search failed')
  } finally {
    loading.value = false
  }
}

function book(r) {
  quick.value = {
    rentalItem: r.rental_item,
    rentalType: r.rental_type,
    rentalUnit: r.rental_unit,
    itemName: r.item_name,
    unitName: r.unit_name,
    start: parseDt(fromInput(q.from)),
    end: parseDt(fromInput(q.to)),
  }
}

function booked(name) {
  quick.value = null
  router.push({ name: 'BookingDetail', params: { name } })
}

onMounted(async () => {
  try {
    Object.assign(options, await api('booking.list_options'))
  } catch {
    /* empty filters */
  }
})
</script>
