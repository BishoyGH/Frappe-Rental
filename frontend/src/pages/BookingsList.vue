<template>
  <PageHeader :title="__('Bookings')">
    <Button variant="solid" :label="__('Create')" data-testid="create" @click="router.push({ name: 'BookingNew' })">
      <template #prefix><LucidePlus class="h-4 w-4" /></template>
    </Button>
  </PageHeader>

  <div class="flex flex-wrap items-center gap-2 border-b px-4 py-2" data-testid="filters">
    <FormControl v-model="filters.search" type="text" :placeholder="__('Search ID or customer')" class="w-48" />
    <FormControl v-model="filters.status" type="select" :options="opt(options.statuses, __('Status: any'))" class="w-36" data-testid="filter-status" />
    <FormControl v-model="filters.rental_type" type="select" :options="opt(options.rental_types, __('Type: any'))" class="w-36" />
    <FormControl v-model="filters.location" type="select" :options="opt(options.locations, __('Location: any'))" class="w-36" />
    <FormControl v-model="filters.from_date" type="date" class="w-36" :title="__('From')" />
    <FormControl v-model="filters.to_date" type="date" class="w-36" :title="__('To')" />
    <span class="flex-1" />
    <FormControl v-model="groupBy" type="select" :options="groupOptions" class="w-36" data-testid="group-by" />
    <FormControl v-model="sort" type="select" :options="sortOptions" class="w-36" data-testid="sort" />
    <Button :tooltip="__('Sort order')" @click="order = order === 'desc' ? 'asc' : 'desc'">
      <LucideArrowDownWideNarrow v-if="order === 'desc'" class="h-4 w-4" />
      <LucideArrowUpNarrowWide v-else class="h-4 w-4" />
    </Button>
    <div class="relative">
      <Button :label="__('Columns')" data-testid="columns" @click="showColumns = !showColumns" />
      <div
        v-if="showColumns"
        class="absolute end-0 z-10 mt-1 w-44 rounded-lg border bg-surface-white p-2 shadow-lg"
        data-testid="columns-menu"
      >
        <label v-for="c in COLUMNS" :key="c.key" class="flex items-center gap-2 rounded px-1 py-1 hover:bg-surface-gray-2">
          <input v-model="visible" type="checkbox" :value="c.key" :disabled="c.key === 'name'" />
          {{ __(c.label) }}
        </label>
      </div>
    </div>
  </div>

  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="rounded bg-surface-red-1 p-3 text-ink-red-4">{{ error }}</div>
    <table v-else class="w-full min-w-[680px] border-collapse" data-testid="bookings-table">
      <thead>
        <tr>
          <th v-for="c in columns" :key="c.key" :class="[th, c.num && 'text-end']">{{ __(c.label) }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="g in grouped" :key="g.key">
          <tr v-if="groupBy" data-testid="group-row">
            <td :colspan="columns.length" class="bg-surface-gray-1 px-2.5 py-1.5 text-sm font-medium text-ink-gray-7">
              {{ g.label }} <span class="ms-1 text-ink-gray-5">{{ g.count }}</span>
            </td>
          </tr>
          <tr
            v-for="r in g.rows"
            :key="r.name"
            class="cursor-pointer hover:bg-surface-gray-1"
            data-testid="booking-row"
            @click="router.push({ name: 'BookingDetail', params: { name: r.name } })"
          >
            <td v-for="c in columns" :key="c.key" :class="[td, c.num && 'text-end tabular-nums']">
              <template v-if="c.key === 'name'"><span class="font-medium text-ink-gray-9">{{ r.name }}</span></template>
              <template v-else-if="c.key === 'customer'">
                <Avatar :label="r.customer_name" size="xs" class="me-1.5 inline-flex align-middle" />{{ r.customer_name }}
              </template>
              <StatusBadge v-else-if="c.key === 'status'" :status="r.status" />
              <template v-else-if="c.key === 'from_datetime' || c.key === 'to_datetime'">{{ fmtDate(r[c.key]) }}</template>
              <template v-else-if="c.key === 'grand_total'">{{ fmtMoney(r.grand_total) }} <span class="text-ink-gray-5">{{ r.currency }}</span></template>
              <template v-else-if="c.key === 'item'">
                {{ r.item }}<span v-if="r.line_count > 1" class="text-ink-gray-5"> +{{ r.line_count - 1 }}</span>
              </template>
              <template v-else>{{ r[c.key] }}</template>
            </td>
          </tr>
        </template>
        <tr v-if="!loading && !rows.length">
          <td :colspan="columns.length" class="py-10 text-center text-ink-gray-5" data-testid="empty">
            {{ __('No bookings match these filters.') }}
          </td>
        </tr>
      </tbody>
    </table>
    <div class="flex items-center gap-3 py-3 text-sm text-ink-gray-5">
      <span data-testid="count">{{ __('{0} of {1}', [rows.length, total]) }}</span>
      <Button v-if="rows.length < total" :label="__('Load more')" :loading="loading" @click="load(true)" />
    </div>
  </div>
</template>

<script setup>
import { Avatar, Button, FormControl } from 'frappe-ui'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import LucideArrowDownWideNarrow from '~icons/lucide/arrow-down-wide-narrow'
import LucideArrowUpNarrowWide from '~icons/lucide/arrow-up-narrow-wide'
import LucidePlus from '~icons/lucide/plus'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate, fmtMoney, store, stored } from '../lib/format'
import { __ } from '../lib/translate'

const router = useRouter()
const th = 'whitespace-nowrap bg-surface-gray-1 px-2.5 py-1.5 text-start text-sm font-medium text-ink-gray-5 first:rounded-s last:rounded-e'
const td = 'whitespace-nowrap border-b px-2.5 py-2 text-base text-ink-gray-7'

const COLUMNS = [
  { key: 'name', label: 'ID' },
  { key: 'customer', label: 'Customer' },
  { key: 'item', label: 'Item' },
  { key: 'rental_type', label: 'Type' },
  { key: 'location', label: 'Location' },
  { key: 'from_datetime', label: 'From' },
  { key: 'to_datetime', label: 'To' },
  { key: 'status', label: 'Status' },
  { key: 'grand_total', label: 'Total', num: true },
]
const DEFAULT_COLUMNS = COLUMNS.filter((c) => c.key !== 'location').map((c) => c.key)
const visible = ref(stored('rental.bookings.columns', DEFAULT_COLUMNS))
const columns = computed(() => COLUMNS.filter((c) => visible.value.includes(c.key)))
const showColumns = ref(false)
watch(visible, (v) => store('rental.bookings.columns', v))

const options = reactive({ statuses: [], rental_types: [], locations: [] })
const opt = (values, placeholder) => [{ label: placeholder, value: '' }, ...values.map((v) => ({ label: __(v), value: v }))]
const groupOptions = [
  { label: __('Group: none'), value: '' },
  { label: __('Group: status'), value: 'status' },
  { label: __('Group: type'), value: 'rental_type' },
  { label: __('Group: location'), value: 'location' },
  { label: __('Group: customer'), value: 'customer' },
]
const sortOptions = [
  { label: __('Sort: created'), value: 'creation' },
  { label: __('Sort: from'), value: 'from_datetime' },
  { label: __('Sort: to'), value: 'to_datetime' },
  { label: __('Sort: total'), value: 'grand_total' },
  { label: __('Sort: ID'), value: 'name' },
]

const filters = reactive({ search: '', status: '', rental_type: '', location: '', from_date: '', to_date: '' })
const groupBy = ref('')
const sort = ref('creation')
const order = ref('desc')
const rows = ref([])
const total = ref(0)
const groups = ref([])
const loading = ref(false)
const error = ref('')
const PAGE = 50

async function load(more = false) {
  loading.value = true
  error.value = ''
  try {
    const res = await api('booking.get_list', {
      filters: JSON.stringify(filters),
      order_by: sort.value,
      order: order.value,
      start: more ? rows.value.length : 0,
      page_length: PAGE,
      group_by: groupBy.value || undefined,
    })
    rows.value = more ? [...rows.value, ...res.rows] : res.rows
    total.value = res.total
    groups.value = res.groups || []
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not load bookings')
  } finally {
    loading.value = false
  }
}

const grouped = computed(() => {
  if (!groupBy.value) return [{ key: 'all', rows: rows.value }]
  const field = groupBy.value
  return groups.value
    .map((g) => ({
      key: g.value || '-',
      label: g.value ? (field === 'status' ? __(g.value) : g.value) : __('Not set'),
      count: g.count,
      rows: rows.value.filter((r) => (r[field] || null) === (g.value || null)),
    }))
    .filter((g) => g.rows.length)
})

let timer
watch(filters, () => {
  clearTimeout(timer)
  timer = setTimeout(() => load(), 250)
})
watch([groupBy, sort, order], () => load())

onMounted(async () => {
  load()
  try {
    Object.assign(options, await api('booking.list_options'))
  } catch {
    /* filters fall back to free values */
  }
})
</script>
