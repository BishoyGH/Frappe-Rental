<template>
  <div class="mx-auto max-w-3xl px-4 py-6" data-testid="mb-detail">
    <router-link :to="{ name: 'MyBookings' }" class="text-sm text-ink-blue-3 hover:underline">← {{ __('My bookings') }}</router-link>
    <div v-if="error" class="my-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="mb-error">{{ error }}</div>
    <div v-if="message" class="my-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="mb-message">{{ message }}</div>

    <template v-if="b">
      <div class="my-3 flex flex-wrap items-center gap-3">
        <h1 class="text-xl font-semibold" data-testid="mb-name">{{ b.name }}</h1>
        <StatusBadge :status="b.status" />
        <span class="text-ink-gray-5">{{ fmtDate(b.from_datetime, true) }} → {{ fmtDate(b.to_datetime, true) }}</span>
      </div>

      <div class="rounded border p-3" data-testid="mb-summary">
        <div v-for="l in b.lines" :key="l.rental_item" class="flex justify-between"><span>{{ l.item_name }} × {{ l.qty }}</span><span>{{ money(l.amount) }}</span></div>
        <div v-for="c in b.charges" :key="c.description" class="flex justify-between text-ink-gray-6"><span>{{ c.description }}</span><span>{{ money(c.amount) }}</span></div>
        <div class="flex justify-between text-ink-gray-6"><span>{{ __('Tax') }}</span><span>{{ money(b.total_taxes) }}</span></div>
        <div class="mt-1 flex justify-between font-semibold"><span>{{ __('Total') }}</span><span data-testid="mb-total">{{ money(b.grand_total) }}</span></div>
      </div>

      <section v-if="b.needs_deposit" class="mt-4" data-testid="mb-deposit">
        <p>{{ __('A deposit of {0} is due.', [money(b.deposit_required - b.deposit_paid)]) }}</p>
        <Button class="mt-2" variant="solid" :label="__('Pay deposit')" :loading="busy" data-testid="mb-pay-deposit" @click="pay('Deposit')" />
      </section>

      <section v-if="b.invoices.length" class="mt-4">
        <h2 class="mb-2 font-semibold">{{ __('Invoices') }}</h2>
        <div v-for="i in b.invoices" :key="i.name" class="flex items-center justify-between border-b py-1.5" data-testid="mb-invoice">
          <span>{{ i.name }} · {{ fmtDate(i.posting_date) }}</span>
          <span class="flex items-center gap-3">
            <span>{{ money(i.grand_total) }}</span>
            <Badge v-if="i.paid" :label="__('Paid')" theme="green" />
            <Button v-else size="sm" variant="solid" :label="__('Pay {0}', [money(i.outstanding_amount)])" :loading="busy" :data-testid="`mb-pay-${i.name}`" @click="pay('Balance', i.name)" />
          </span>
        </div>
      </section>

      <section v-if="b.documents.length" class="mt-4">
        <h2 class="mb-2 font-semibold">{{ __('Documents') }}</h2>
        <a v-for="d in b.documents" :key="d.ref" :href="downloadUrl(d)" class="me-4 text-ink-blue-3 hover:underline" data-testid="mb-doc">{{ d.label }}</a>
      </section>

      <section v-if="b.can_change" class="mt-4" data-testid="mb-change">
        <h2 class="mb-2 font-semibold">{{ __('Change dates') }}</h2>
        <div class="flex flex-wrap items-end gap-2">
          <FormControl v-model="from" type="datetime-local" :label="__('From')" data-testid="mb-from" />
          <FormControl v-model="to" type="datetime-local" :label="__('To')" data-testid="mb-to" />
          <Button :label="__('Save')" :loading="busy" data-testid="mb-save" @click="change" />
        </div>
      </section>

      <section v-if="b.can_cancel" class="mt-4">
        <Button v-if="!preview" theme="red" :label="__('Cancel booking')" :loading="busy" data-testid="mb-cancel" @click="showPreview" />
        <div v-else class="rounded border border-red-300 p-3" data-testid="mb-preview">
          <p v-if="preview.held">{{ __('This releases your held dates. Nothing is charged.') }}</p>
          <template v-else>
            <p>{{ __('You get back {0}.', [money(preview.refund)]) }}</p>
            <p v-if="Number(preview.kept)" class="text-ink-gray-6">{{ __('We keep {0} under the cancellation policy.', [money(preview.kept)]) }}</p>
          </template>
          <div class="mt-2 flex gap-2">
            <Button theme="red" variant="solid" :label="__('Yes, cancel')" :loading="busy" data-testid="mb-confirm-cancel" @click="cancel" />
            <Button :label="__('Keep booking')" @click="preview = null" />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { Badge, Button, FormControl } from 'frappe-ui'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true } })
const route = useRoute()
const b = ref(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const preview = ref(null)
const from = ref('')
const to = ref('')

const money = (v) => `${Number(v || 0).toFixed(2)} ${b.value?.currency || ''}`
const toServer = (v) => (v ? String(v).replace('T', ' ') + (String(v).length === 16 ? ':00' : '') : '')
const toInput = (v) => String(v || '').replace(' ', 'T').slice(0, 16)
const errText = (e) => e.messages?.[0] || e.message || __('Something went wrong')
const downloadUrl = (d) => `/api/method/frappe_rental.api.portal.download?name=${encodeURIComponent(props.name)}&kind=${d.kind}&ref=${encodeURIComponent(d.ref)}`

function show(detail) {
  b.value = detail
  from.value = toInput(detail.from_datetime)
  to.value = toInput(detail.to_datetime)
}

async function run(fn, done) {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await fn()
    if (done) message.value = done
  } catch (e) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}

const load = () => run(async () => show(await api('portal.detail', { name: props.name })))
const change = () => run(async () => show(await api('portal.change', { name: props.name, from_datetime: toServer(from.value), to_datetime: toServer(to.value) })), __('Dates changed'))
const showPreview = () => run(async () => (preview.value = await api('portal.cancel_preview', { name: props.name })))
const cancel = () =>
  run(async () => {
    show(await api('portal.cancel', { name: props.name }))
    preview.value = null
  }, __('Booking cancelled'))
const pay = (purpose, invoice) =>
  run(async () => {
    const out = await api('checkout.pay', { name: props.name, purpose, ...(invoice ? { invoice } : {}) })
    window.location.href = out.payment_url
  })

onMounted(async () => {
  if (route.query.cancelled) error.value = __('Payment was cancelled. You can try again.')
  await load()
  if (route.query.paid && !error.value) message.value = __('Thank you. We will confirm your payment shortly.')
})
</script>
