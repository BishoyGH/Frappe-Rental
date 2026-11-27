<template>
  <div class="fixed inset-0 z-30 grid place-items-center bg-black/30 p-4" data-testid="quick-book" @mousedown.self="$emit('close')">
    <div class="w-full max-w-md rounded-xl bg-surface-white p-5 shadow-xl">
      <h2 class="mb-1 text-lg font-semibold">{{ __('Quick book') }}</h2>
      <p class="mb-4 text-ink-gray-5">{{ itemName }}<span v-if="unitName"> · {{ unitName }}</span></p>
      <div class="flex flex-col gap-3">
        <div>
          <label class="mb-1 block text-sm text-ink-gray-5">{{ __('Customer') }}</label>
          <LinkPicker v-model="customer" doctype="Customer" :placeholder="__('Search customers')" data-testid="qb-customer" />
        </div>
        <FormControl v-model="from" type="datetime-local" :label="__('From')" data-testid="qb-from" />
        <FormControl v-model="to" type="datetime-local" :label="__('To')" data-testid="qb-to" />
        <p v-if="price !== null" class="text-ink-gray-7" data-testid="qb-price">
          {{ __('Price') }}: <b>{{ fmtMoney(price) }} {{ currency }}</b>
        </p>
        <div v-if="error" class="rounded bg-surface-red-1 p-2 text-ink-red-4" data-testid="qb-error">{{ error }}</div>
      </div>
      <div class="mt-5 flex justify-end gap-2">
        <Button :label="__('Close')" @click="$emit('close')" />
        <Button variant="solid" :label="__('Hold')" :loading="saving" :disabled="!customer || !from || !to" data-testid="qb-save" @click="save" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { ref, watch } from 'vue'
import { api } from '../lib/api'
import { fmtMoney, fromInput, toInput } from '../lib/format'
import { __ } from '../lib/translate'
import LinkPicker from './LinkPicker.vue'

const props = defineProps({
  rentalItem: String,
  rentalType: String,
  rentalUnit: String,
  itemName: String,
  unitName: String,
  start: Date,
  end: Date,
})
const emit = defineEmits(['close', 'booked'])
const customer = ref('')
const from = ref(toInput(props.start))
const to = ref(toInput(props.end))
const price = ref(null)
const currency = ref('')
const error = ref('')
const saving = ref(false)

const booking = () => ({
  customer: customer.value,
  rental_type: props.rentalType,
  from_datetime: fromInput(from.value),
  to_datetime: fromInput(to.value),
  lines: [{ rental_item: props.rentalItem, rental_unit: props.rentalUnit || undefined, qty: 1 }],
})

async function requote() {
  if (!customer.value || !from.value || !to.value) return (price.value = null)
  try {
    const q = await api('booking.quote', { booking: JSON.stringify(booking()) })
    price.value = q.grand_total
    currency.value = q.currency
    error.value = ''
  } catch (e) {
    price.value = null
    error.value = e.messages?.[0] || __('Could not price this booking')
  }
}
watch([customer, from, to], requote)

async function save() {
  saving.value = true
  error.value = ''
  try {
    const res = await api('booking.create', { booking: JSON.stringify(booking()), hold: 1 })
    emit('booked', res.name)
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not book')
  } finally {
    saving.value = false
  }
}
</script>
