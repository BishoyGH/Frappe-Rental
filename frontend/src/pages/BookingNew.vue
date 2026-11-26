<template>
  <PageHeader :title="__('New booking')" :parent="{ label: __('Bookings'), to: { name: 'Bookings' } }">
    <Button :label="__('Save draft')" :loading="saving === 'draft'" :disabled="!ready" data-testid="save-draft" @click="save(0)" />
    <Button variant="solid" :label="__('Save and hold')" :loading="saving === 'hold'" :disabled="!ready" data-testid="save-hold" @click="save(1)" />
  </PageHeader>

  <div class="grid min-h-0 flex-1 overflow-auto lg:grid-cols-[minmax(0,1fr)_280px]">
    <section class="min-w-0 p-4">
      <div v-if="error" class="mb-3 rounded bg-surface-red-1 p-3 text-ink-red-4" data-testid="error">{{ error }}</div>
      <div class="mb-5 grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-x-5 gap-y-3">
        <div>
          <label class="mb-1 block text-sm text-ink-gray-5">{{ __('Customer') }}</label>
          <LinkPicker v-model="form.customer" doctype="Customer" :placeholder="__('Search customers')" data-testid="customer" />
        </div>
        <FormControl v-model="form.rental_type" type="select" :label="__('Item type')" :options="typeOptions" data-testid="rental-type" />
        <FormControl v-model="form.location" type="select" :label="__('Location')" :options="locationOptions" />
        <FormControl v-model="form.from_datetime" type="datetime-local" :label="__('From')" data-testid="from" />
        <FormControl v-model="form.to_datetime" type="datetime-local" :label="__('To')" data-testid="to" />
      </div>

      <h3 class="mb-2 font-semibold">{{ __('Items') }}</h3>
      <div v-for="(l, i) in form.lines" :key="l.key" class="mb-2 grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_80px_32px] items-end gap-2" data-testid="line">
        <LinkPicker v-model="l.rental_item" doctype="Rental Item" :placeholder="__('Item')" data-testid="line-item" />
        <LinkPicker v-model="l.rental_unit" doctype="Rental Unit" :rental-item="l.rental_item" :placeholder="__('Unit (optional)')" data-testid="line-unit" />
        <FormControl v-model="l.qty" type="number" min="1" />
        <Button :disabled="form.lines.length === 1" :tooltip="__('Remove')" @click="form.lines.splice(i, 1)">
          <LucideX class="h-4 w-4" />
        </Button>
      </div>
      <Button :label="__('Add item')" @click="addLine"><template #prefix><LucidePlus class="h-4 w-4" /></template></Button>
    </section>

    <aside class="border-t bg-surface-gray-1 p-4 lg:border-l lg:border-t-0" data-testid="quote">
      <h3 class="mb-2 font-semibold">{{ __('Price') }}</h3>
      <p v-if="!quote" class="text-ink-gray-5">{{ quoteError || __('Pick a customer, dates and an item to see the price.') }}</p>
      <template v-else>
        <div v-for="(l, i) in quote.lines" :key="i" class="flex justify-between py-1">
          <span class="text-ink-gray-5">{{ l.units }} × {{ __(l.time_unit) }}</span><span class="tabular-nums">{{ fmtMoney(l.amount) }}</span>
        </div>
        <div v-for="c in quote.charges" :key="c.charge" class="flex justify-between py-1">
          <span class="text-ink-gray-5">{{ c.charge }}</span><span class="tabular-nums">{{ fmtMoney(c.amount) }}</span>
        </div>
        <div class="flex justify-between py-1"><span class="text-ink-gray-5">{{ __('Taxes') }}</span><span class="tabular-nums">{{ fmtMoney(quote.total_taxes) }}</span></div>
        <div class="mt-1 flex justify-between border-t pt-2 font-semibold" data-testid="quote-total">
          <span>{{ __('Total {0}', [quote.currency || '']) }}</span><span class="tabular-nums">{{ fmtMoney(quote.grand_total) }}</span>
        </div>
        <div v-if="quote.deposit_required" class="flex justify-between py-1">
          <span class="text-ink-gray-5">{{ __('Deposit') }}</span><span class="tabular-nums">{{ fmtMoney(quote.deposit_required) }}</span>
        </div>
      </template>
    </aside>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import LucidePlus from '~icons/lucide/plus'
import LucideX from '~icons/lucide/x'
import LinkPicker from '../components/LinkPicker.vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { fmtMoney } from '../lib/format'
import { __ } from '../lib/translate'

const router = useRouter()
let seq = 0
const newLine = () => ({ key: ++seq, rental_item: '', rental_unit: '', qty: 1 })
const form = reactive({ customer: '', rental_type: '', location: '', from_datetime: '', to_datetime: '', lines: [newLine()] })
const addLine = () => form.lines.push(newLine())
const options = reactive({ rental_types: [], locations: [] })
const typeOptions = computed(() => [{ label: __('Select'), value: '' }, ...options.rental_types.map((v) => ({ label: v, value: v }))])
const locationOptions = computed(() => [{ label: __('Any'), value: '' }, ...options.locations.map((v) => ({ label: v, value: v }))])
const saving = ref('')
const error = ref('')
const quote = ref(null)
const quoteError = ref('')

const toServer = (v) => (v ? v.replace('T', ' ') + (v.length === 16 ? ':00' : '') : '')
const payload = () => ({
  customer: form.customer,
  rental_type: form.rental_type,
  location: form.location,
  from_datetime: toServer(form.from_datetime),
  to_datetime: toServer(form.to_datetime),
  lines: form.lines
    .filter((l) => l.rental_item)
    .map((l) => ({ rental_item: l.rental_item, rental_unit: l.rental_unit || undefined, qty: Number(l.qty) || 1 })),
})
const ready = computed(() => form.customer && form.rental_type && form.from_datetime && form.to_datetime && form.lines.some((l) => l.rental_item))

let timer
watch(
  form,
  () => {
    clearTimeout(timer)
    if (!ready.value) {
      quote.value = null
      return
    }
    timer = setTimeout(async () => {
      try {
        quote.value = await api('booking.quote', { booking: JSON.stringify(payload()) })
        quoteError.value = ''
      } catch (e) {
        quote.value = null
        quoteError.value = e.messages?.[0] || __('Could not price this booking')
      }
    }, 300)
  },
  { deep: true },
)

async function save(hold) {
  saving.value = hold ? 'hold' : 'draft'
  error.value = ''
  try {
    const res = await api('booking.create', { booking: JSON.stringify(payload()), hold })
    router.push({ name: 'BookingDetail', params: { name: res.name } })
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not save the booking')
  } finally {
    saving.value = ''
  }
}

onMounted(async () => {
  try {
    Object.assign(options, await api('booking.list_options'))
  } catch {
    /* leave empty */
  }
})
</script>
