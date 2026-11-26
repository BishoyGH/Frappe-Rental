<template>
  <PageHeader :title="__('Handovers')" />

  <form class="flex flex-wrap items-end gap-2 border-b px-4 py-2" @submit.prevent="lookup">
    <FormControl
      ref="scanBox"
      v-model="code"
      type="text"
      :label="__('Scan a booking, barcode or serial')"
      class="w-80"
      autofocus
      data-testid="ho-scan"
    />
    <Button type="submit" variant="solid" :label="booking ? __('Add') : __('Find')" :loading="loading" data-testid="ho-find" />
    <Button v-if="booking" :label="__('Clear')" @click="reset" />
  </form>

  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="ho-error">{{ error }}</div>
    <div v-if="message" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="ho-message">{{ message }}</div>

    <template v-if="booking">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <router-link :to="{ name: 'BookingDetail', params: { name: booking.name } }" class="text-lg font-semibold text-ink-gray-9 hover:underline" data-testid="ho-booking">
          {{ booking.name }}
        </router-link>
        <StatusBadge :status="booking.status" />
        <span class="text-ink-gray-6">{{ booking.customer_name }}</span>
        <span class="text-ink-gray-5">{{ fmtDate(booking.from_datetime, true) }} → {{ fmtDate(booking.to_datetime, true) }}</span>
      </div>

      <p v-if="!booking.next_step" class="text-ink-gray-5" data-testid="ho-done">{{ __('Nothing to hand over for this booking.') }}</p>
      <template v-else>
        <h3 class="mb-2 font-semibold" data-testid="ho-step">{{ booking.next_step === 'Return' ? __('Return') : __('Check-out') }}</h3>
        <table class="w-full min-w-[640px] border-collapse" data-testid="ho-lines">
          <thead>
            <tr>
              <th :class="th">{{ __('Scanned') }}</th>
              <th :class="th">{{ __('Unit') }}</th>
              <th :class="th">{{ __('Serial / barcode') }}</th>
              <th v-if="isReturn" :class="th">{{ __('Condition') }}</th>
              <th v-if="isReturn" :class="th">{{ __('Notes') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in eligible" :key="l.rental_unit" data-testid="ho-line">
              <td :class="td"><input v-model="l.picked" type="checkbox" :aria-label="__('Scanned')" :data-testid="`ho-pick-${l.rental_unit}`" /></td>
              <td :class="td">{{ l.unit_name }}</td>
              <td :class="td">{{ l.serial_no || l.barcode || '-' }}</td>
              <td v-if="isReturn" :class="td">
                <select v-model="l.condition" :aria-label="__('Condition')" class="rounded border-gray-300 py-1 text-base" :data-testid="`ho-cond-${l.rental_unit}`">
                  <option v-for="c in CONDITIONS" :key="c" :value="c">{{ __(c) }}</option>
                </select>
              </td>
              <td v-if="isReturn" :class="td"><input v-model="l.notes" :aria-label="__('Notes')" class="w-full rounded border-gray-300 py-1 text-base" /></td>
            </tr>
          </tbody>
        </table>
        <div class="mt-3 flex gap-2">
          <Button variant="solid" :disabled="!picked.length" :loading="submitting" :label="submitLabel" data-testid="ho-submit" @click="submit" />
          <Button :label="__('Pick all')" @click="eligible.forEach((l) => (l.picked = true))" />
        </div>
      </template>

      <template v-if="booking.history.length">
        <h3 class="mb-2 mt-6 font-semibold">{{ __('History') }}</h3>
        <div v-for="h in booking.history" :key="h.name" class="flex gap-3 py-1 text-ink-gray-7" data-testid="ho-history">
          <span class="w-24">{{ __(h.handover_type) }}</span>
          <span>{{ fmtDate(h.posted_on, true) }}</span>
          <Badge v-if="h.is_late" :label="__('Late {0} min', [h.late_minutes])" theme="orange" />
        </div>
      </template>
    </template>

    <template v-else>
      <div class="grid gap-6 md:grid-cols-2">
        <section v-for="(list, key) in today" :key="key">
          <h3 class="mb-2 font-semibold">{{ key === 'outgoing' ? __('To hand out') : __('To take back') }}</h3>
          <div v-for="r in list" :key="r.name" class="flex justify-between border-b py-1.5" :data-testid="`ho-${key}`">
            <button class="text-ink-blue-3 hover:underline" @click="open(r.name)">{{ r.name }}</button>
            <span class="text-ink-gray-5">{{ fmtDate(key === 'outgoing' ? r.from_datetime : r.to_datetime, true) }}</span>
          </div>
          <p v-if="!list.length" class="text-ink-gray-5">{{ __('Nothing due.') }}</p>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { Badge, Button, FormControl } from 'frappe-ui'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const CONDITIONS = ['Good', 'Damaged', 'Missing']
const th = 'bg-surface-gray-1 px-2.5 py-1.5 text-start text-sm font-medium text-ink-gray-5'
const td = 'border-b px-2.5 py-2 text-ink-gray-7'

const code = ref('')
const booking = ref(null)
const today = ref({ outgoing: [], incoming: [] })
const loading = ref(false)
const submitting = ref(false)
const error = ref('')
const message = ref('')

const isReturn = computed(() => booking.value?.next_step === 'Return')
const eligible = computed(() => (booking.value?.lines || []).filter((l) => (isReturn.value ? l.out : !l.out)))
const picked = computed(() => eligible.value.filter((l) => l.picked))
const submitLabel = computed(() =>
  isReturn.value ? __('Take back {0}', [picked.value.length]) : __('Hand out {0}', [picked.value.length]),
)

const errText = (e) => e.messages?.[0] || e.message || __('Something went wrong')

function load(state) {
  booking.value = state
  for (const l of state.lines) {
    l.picked = false
    l.condition = 'Good'
    l.notes = ''
  }
}

function matchLine(c) {
  const v = c.trim().toLowerCase()
  return eligible.value.find((l) => [l.rental_unit, l.serial_no, l.barcode, l.unit_name].some((x) => x && String(x).toLowerCase() === v))
}

async function lookup() {
  error.value = ''
  message.value = ''
  const c = code.value.trim()
  if (!c) return
  if (booking.value) {
    const line = matchLine(c)
    if (line) {
      line.picked = true
      code.value = ''
      return
    }
  }
  loading.value = true
  try {
    const state = await api('ops.find_booking', { code: c })
    if (!state) error.value = __('No open booking found for {0}', [c])
    else {
      load(state)
      const line = matchLine(c)
      if (line) line.picked = true
    }
    code.value = ''
  } catch (e) {
    error.value = errText(e)
  } finally {
    loading.value = false
  }
}

async function open(name) {
  error.value = ''
  try {
    load(await api('ops.handover_state', { name }))
  } catch (e) {
    error.value = errText(e)
  }
}

async function submit() {
  submitting.value = true
  error.value = ''
  const lines = picked.value.map((l) => ({
    rental_unit: l.rental_unit,
    qty: l.qty,
    ...(isReturn.value ? { condition: l.condition, notes: l.notes } : {}),
  }))
  try {
    const out = await api(isReturn.value ? 'booking.checkin' : 'booking.checkout', { name: booking.value.name, lines: JSON.stringify(lines) })
    message.value = __('{0} saved', [out.name])
    load(await api('ops.handover_state', { name: booking.value.name }))
  } catch (e) {
    error.value = errText(e)
  } finally {
    submitting.value = false
  }
}

function reset() {
  booking.value = null
  message.value = ''
  error.value = ''
  loadToday()
}

async function loadToday() {
  try {
    today.value = await api('ops.todays_handovers')
  } catch (e) {
    error.value = errText(e)
  }
}

const route = useRoute()
onMounted(() => (route.query.booking ? open(route.query.booking) : loadToday()))
</script>
