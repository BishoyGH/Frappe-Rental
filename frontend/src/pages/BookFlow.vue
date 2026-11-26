<template>
  <div class="mx-auto max-w-2xl px-4 py-6" data-testid="book-flow">
    <div class="mb-4 flex items-center justify-between">
      <h1 class="text-xl font-semibold">{{ quote?.item_name ? __('Book {0}', [quote.item_name]) : __('Book') }}</h1>
      <span v-if="boot.user && boot.user !== 'Guest'" class="text-ink-gray-5" data-testid="book-user">{{ boot.full_name || boot.user }}</span>
      <a v-else :href="loginUrl" class="text-ink-blue-3 hover:underline" data-testid="book-login">{{ __('Sign in') }}</a>
    </div>

    <ol class="mb-5 flex flex-wrap gap-2 text-sm">
      <li v-for="(s, i) in steps" :key="s" :aria-current="i === stepIndex ? 'step' : undefined" :class="['rounded px-2 py-0.5', i === stepIndex ? 'bg-surface-gray-3 font-medium' : 'text-ink-gray-5']">
        {{ i + 1 }}. {{ __(s) }}
      </li>
    </ol>

    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="book-error">{{ error }}</div>

    <!-- 1. dates -->
    <section v-if="step === 'Dates'" class="space-y-3">
      <FormControl v-model="form.from" type="datetime-local" :label="__('From')" data-testid="book-from" />
      <FormControl v-model="form.to" type="datetime-local" :label="__('To')" data-testid="book-to" />
      <FormControl v-model="form.qty" type="number" :label="__('Quantity')" data-testid="book-qty" />
      <Button variant="solid" :label="__('Continue')" :loading="busy" data-testid="book-next" @click="checkDates" />
    </section>

    <!-- 2. extras -->
    <section v-if="step === 'Extras'" class="space-y-2">
      <p v-if="!extraOptions.length" class="text-ink-gray-5">{{ __('No extras for this item.') }}</p>
      <label v-for="e in extraOptions" :key="e.charge" class="flex items-center gap-2" :data-testid="`book-extra-${e.label}`">
        <input v-model="form.extras" type="checkbox" :value="e.charge" />
        <span>{{ e.label }}</span>
        <span class="text-ink-gray-5">{{ e.charge_type === 'Percent' ? `${e.percent}%` : fmtMoney(e.amount) }}</span>
      </label>
      <div class="flex gap-2 pt-2">
        <Button :label="__('Back')" @click="step = 'Dates'" />
        <Button variant="solid" :label="__('Continue')" data-testid="book-next" @click="step = 'Details'" />
      </div>
    </section>

    <!-- 3. details -->
    <section v-if="step === 'Details'" class="space-y-3">
      <template v-if="isGuest">
        <FormControl v-model="form.full_name" type="text" :label="__('Full name')" data-testid="book-name" />
        <FormControl v-model="form.email" type="email" :label="__('Email')" data-testid="book-email" />
        <FormControl v-model="form.phone" type="tel" :label="__('Phone')" data-testid="book-phone" />
        <p class="text-sm text-ink-gray-5">
          {{ __('Booked with us before?') }} <a :href="loginUrl" class="text-ink-blue-3 hover:underline">{{ __('Sign in') }}</a>
        </p>
      </template>
      <p v-else data-testid="book-as">{{ __('Booking as {0}', [boot.full_name || boot.user]) }}</p>
      <div class="rounded border p-3" data-testid="book-quote">
        <div class="flex justify-between"><span>{{ fmtDate(toServer(form.from), true) }} → {{ fmtDate(toServer(form.to), true) }}</span><span>× {{ form.qty }}</span></div>
        <div class="mt-1 flex justify-between font-medium"><span>{{ __('From') }}</span><span>{{ fmtMoney(quote?.grand_total) }}</span></div>
      </div>
      <div class="flex gap-2">
        <Button :label="__('Back')" @click="step = 'Extras'" />
        <Button variant="solid" :label="__('Hold my booking')" :loading="busy" data-testid="book-start" @click="startBooking" />
      </div>
    </section>

    <!-- 4. sign -->
    <section v-if="step === 'Sign'" class="space-y-3">
      <div class="prose max-h-80 overflow-auto rounded border p-3" data-testid="book-terms" v-html="state.contract?.html" />
      <FormControl v-model="form.signer" type="text" :label="__('Type your full name to sign')" data-testid="book-signer" />
      <Button variant="solid" :label="__('Sign')" :loading="busy" data-testid="book-sign" @click="signContract" />
    </section>

    <!-- 5. pay / confirm -->
    <section v-if="step === 'Pay'" class="space-y-3">
      <Summary :state="state" />
      <p v-if="state.hold_expires_on" class="text-sm text-ink-gray-5">{{ __('We hold this booking until {0}.', [fmtDate(state.hold_expires_on, true)]) }}</p>
      <template v-if="state.needs_deposit">
        <p>{{ __('A deposit of {0} confirms this booking.', [fmtMoney(state.deposit_required)]) }}</p>
        <Button variant="solid" :label="__('Pay deposit')" :loading="busy" data-testid="book-pay" @click="pay" />
      </template>
      <Button v-else variant="solid" :label="__('Confirm booking')" :loading="busy" data-testid="book-confirm" @click="confirm" />
    </section>

    <!-- 6. done -->
    <section v-if="step === 'Done'" class="space-y-3" data-testid="book-done">
      <p class="text-lg font-medium">{{ __('Booking {0} is confirmed.', [state.name]) }}</p>
      <Summary :state="state" />
      <a href="/rental/my-bookings" class="text-ink-blue-3 hover:underline">{{ __('My bookings') }}</a>
    </section>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { boot } from '../boot'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const route = useRoute()
const item = route.query.item
const form = reactive({
  from: route.query.from || '',
  to: route.query.to || '',
  qty: Number(route.query.qty) || 1,
  extras: [],
  full_name: '',
  email: '',
  phone: '',
  signer: '',
})
const step = ref('Dates')
const quote = ref(null)
const extraOptions = ref([])
const state = ref({})
const busy = ref(false)
const error = ref('')

const isGuest = computed(() => !boot.user || boot.user === 'Guest')
const steps = computed(() => ['Dates', 'Extras', 'Details', ...(state.value.contract ? ['Sign'] : []), 'Pay', 'Done'])
const stepIndex = computed(() => steps.value.indexOf(step.value))
const loginUrl = computed(() => '/login?redirect-to=' + encodeURIComponent(window.location.pathname + window.location.search))

const toServer = (v) => (v ? String(v).replace('T', ' ') + (String(v).length === 16 ? ':00' : '') : '')
const fmtMoney = (v) => (v == null ? '' : `${Number(v).toFixed(2)} ${quote.value?.currency || state.value.currency || ''}`)
const errText = (e) => e.messages?.[0] || e.message || __('Something went wrong')

async function run(fn) {
  busy.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}

const checkDates = () =>
  run(async () => {
    if (!form.from || !form.to) throw new Error(__('Choose your dates'))
    const q = await api('public.quote', { item, from_datetime: toServer(form.from), to_datetime: toServer(form.to), qty: form.qty })
    quote.value = q
    if (!q.available) throw new Error(__('Not available for these dates'))
    extraOptions.value = await api('checkout.extras', { item })
    step.value = 'Extras'
  })

function afterState(s) {
  state.value = s
  if (s.docstatus === 1) step.value = 'Done'
  else if (s.needs_signature) step.value = 'Sign'
  else step.value = 'Pay'
}

const startBooking = () =>
  run(async () => {
    const out = await api('checkout.start', {
      booking: JSON.stringify({
        item,
        from_datetime: toServer(form.from),
        to_datetime: toServer(form.to),
        qty: form.qty,
        extras: form.extras,
        details: { full_name: form.full_name, email: form.email, phone: form.phone },
      }),
    })
    if (out.csrf_token) window.csrf_token = out.csrf_token
    if (out.new_user) Object.assign(boot, { user: form.email, full_name: form.full_name })
    afterState(out)
  })

const signContract = () => run(async () => afterState(await api('checkout.sign', { name: state.value.name, signer_name: form.signer, signature: form.signer })))
const confirm = () => run(async () => afterState(await api('checkout.finish', { name: state.value.name })))
const pay = () =>
  run(async () => {
    const out = await api('checkout.pay', { name: state.value.name })
    if (out.payment_url) window.location.href = out.payment_url
    else afterState(out)
  })

const Summary = defineComponent({
  props: { state: { type: Object, required: true } },
  setup(props) {
    return () =>
      h('div', { class: 'rounded border p-3', 'data-testid': 'book-summary' }, [
        ...(props.state.lines || []).map((l) => h('div', { class: 'flex justify-between' }, [h('span', `${l.item_name} × ${l.qty}`), h('span', fmtMoney(l.amount))])),
        ...(props.state.charges || []).map((c) => h('div', { class: 'flex justify-between text-ink-gray-6' }, [h('span', c.description), h('span', fmtMoney(c.amount))])),
        h('div', { class: 'flex justify-between text-ink-gray-6' }, [h('span', __('Tax')), h('span', fmtMoney(props.state.total_taxes))]),
        h('div', { class: 'mt-1 flex justify-between font-semibold', 'data-testid': 'book-total' }, [h('span', __('Total')), h('span', fmtMoney(props.state.grand_total))]),
      ])
  },
})

onMounted(() => {
  if (!item) error.value = __('Choose an item on the rentals page first.')
  else if (route.query.booking) resume(route.query.booking)
})

// Back from the payment page: the provider's webhook may land a moment after the redirect.
async function resume(name) {
  if (route.query.cancelled) error.value = __('Payment was cancelled. You can try again.')
  for (let i = 0; i < (route.query.paid ? 10 : 1); i++) {
    await run(async () => afterState(await api('checkout.summary', { name })))
    if (!state.value.needs_deposit) return
    await new Promise((r) => setTimeout(r, 1500))
  }
  if (route.query.paid) error.value = __('We have not received the payment confirmation yet. Refresh in a minute.')
}
</script>
