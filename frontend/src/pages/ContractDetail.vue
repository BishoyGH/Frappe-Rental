<template>
  <PageHeader :title="name" :parent="{ label: __('Contracts'), to: { name: 'Contracts' } }">
    <template #title-extra><StatusBadge v-if="c" :status="c.status" /></template>
    <Button v-if="c?.actions.send_for_signature" variant="solid" :label="__('Send for signature')" :loading="busy" data-testid="ct-send" @click="act('contract.request_signature')" />
    <Button v-if="c?.actions.countersign" variant="solid" :label="__('Countersign')" :loading="busy" data-testid="ct-countersign" @click="act('contract.countersign')" />
  </PageHeader>

  <nav class="flex gap-4 border-b px-4" data-testid="tabs">
    <button
      v-for="t in TABS"
      :key="t"
      class="py-2"
      :class="tab === t ? 'font-medium text-ink-gray-9 shadow-[inset_0_-2px_0_theme(colors.gray.900)]' : 'text-ink-gray-5'"
      :data-testid="`tab-${t}`"
      @click="tab = t"
    >{{ __(t) }}</button>
  </nav>

  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="ct-error">{{ error }}</div>
    <template v-if="c">
      <div v-if="tab === 'Overview'" class="grid max-w-3xl grid-cols-2 gap-x-8 gap-y-1" data-testid="ct-overview">
        <template v-for="[label, value] in overview" :key="label">
          <span class="text-ink-gray-5">{{ __(label) }}</span><span>{{ value }}</span>
        </template>
      </div>

      <div v-else-if="tab === 'Terms'" data-testid="ct-terms">
        <p v-if="c.terms.template" class="mb-2 text-sm text-ink-gray-5">{{ c.terms.template }} · v{{ c.terms.version || 1 }}</p>
        <div v-if="c.terms.html" class="prose max-w-3xl" v-html="c.terms.html" />
        <p v-else class="text-ink-gray-5">{{ __('Terms are written when the contract is sent for signature.') }}</p>
        <h3 v-if="c.amendments.length" class="mb-1 mt-4 font-semibold">{{ __('Amendments') }}</h3>
        <div v-for="a in c.amendments" :key="a.effective_date + a.reason" class="text-ink-gray-7">{{ fmtDate(a.effective_date) }} · {{ a.reason }}</div>
      </div>

      <table v-else-if="tab === 'Allocations'" class="w-full min-w-[640px] border-collapse" data-testid="ct-allocations">
        <thead><tr><th v-for="h in ['Type', 'Item / unit', 'From', 'To', 'Qty / capacity', 'Status']" :key="h" :class="th">{{ __(h) }}</th></tr></thead>
        <tbody>
          <tr v-for="a in c.allocations" :key="a.name">
            <td :class="td">{{ a.allocation_type }}</td>
            <td :class="td">{{ a.rental_unit || a.rental_item }}</td>
            <td :class="td">{{ fmtDate(a.from_date) }}</td>
            <td :class="td">{{ fmtDate(a.to_date) }}</td>
            <td :class="td">{{ a.capacity ? `${a.capacity_used || 0} / ${a.capacity}` : a.qty }}</td>
            <td :class="td">{{ a.status }}</td>
          </tr>
          <tr v-if="!c.allocations.length"><td colspan="6" :class="td + ' text-ink-gray-5'">{{ __('Nothing allocated.') }}</td></tr>
        </tbody>
      </table>

      <div v-else-if="tab === 'Billing'" data-testid="ct-billing">
        <div v-if="c.billing.plan" class="mb-4 max-w-3xl">
          <h3 class="mb-1 font-semibold">{{ __('Billing plan') }}</h3>
          <div>{{ c.billing.plan.frequency }} · {{ c.billing.plan.timing }} · {{ c.billing.plan.alignment }}</div>
        </div>
        <p v-else class="mb-4 text-ink-gray-5">{{ __('No billing plan on this contract.') }}</p>
      </div>

      <div v-else data-testid="ct-visits">
        <table class="w-full min-w-[640px] border-collapse">
          <thead><tr><th v-for="h in ['Planned', 'Type', 'Status', 'Technician', 'Response due', 'SLA']" :key="h" :class="th">{{ __(h) }}</th></tr></thead>
          <tbody>
            <tr v-for="v in c.visits" :key="v.name">
              <td :class="td">{{ fmtDate(v.planned_date) }}</td>
              <td :class="td">{{ v.visit_type }}</td>
              <td :class="td"><StatusBadge :status="v.status" /></td>
              <td :class="td">{{ v.technician || '–' }}</td>
              <td :class="td">{{ v.response_due ? fmtDate(v.response_due, true) : '–' }}</td>
              <td :class="td"><Badge v-if="v.sla_breached" :label="__('Breached')" theme="red" /></td>
            </tr>
            <tr v-if="!c.visits.length"><td colspan="6" :class="td + ' text-ink-gray-5'">{{ __('No visits.') }}</td></tr>
          </tbody>
        </table>
      </div>

      <template v-if="tab === 'Billing' || tab === 'Bookings and visits'">
        <h3 v-if="tab === 'Billing'" class="mb-1 font-semibold">{{ __('Bookings under this contract') }}</h3>
        <h3 v-else class="mb-1 mt-6 font-semibold">{{ __('Bookings') }}</h3>
        <router-link v-for="b in c.billing.bookings" :key="b.name" :to="{ name: 'BookingDetail', params: { name: b.name } }" class="flex max-w-3xl justify-between border-b py-1.5 hover:bg-surface-gray-1" data-testid="ct-booking">
          <span class="text-ink-blue-3">{{ b.name }}</span>
          <span class="text-ink-gray-6">{{ fmtDate(b.from_datetime, true) }} → {{ fmtDate(b.to_datetime, true) }}</span>
          <span>{{ Number(b.grand_total).toFixed(2) }} {{ b.currency }} · <StatusBadge :status="b.status" /></span>
        </router-link>
        <p v-if="!c.billing.bookings.length" class="text-ink-gray-5">{{ __('No bookings yet.') }}</p>
      </template>
    </template>
  </div>
</template>

<script setup>
import { Badge, Button } from 'frappe-ui'
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true } })
const TABS = ['Overview', 'Terms', 'Allocations', 'Billing', 'Bookings and visits']
const th = 'bg-surface-gray-1 px-2.5 py-1.5 text-left text-sm font-medium text-ink-gray-5'
const td = 'border-b px-2.5 py-2 text-ink-gray-7'
const tab = ref('Overview')
const c = ref(null)
const busy = ref(false)
const error = ref('')

const yn = (v) => (v ? __('Yes') : __('No'))
const overview = computed(() => {
  const x = c.value
  if (!x) return []
  return [
    ['Customer', x.customer_name],
    ['Type', x.rental_type || '–'],
    ['Term', `${fmtDate(x.start_date)} → ${x.open_ended ? __('open-ended') : fmtDate(x.end_date)}`],
    ['Auto-renew', x.auto_renew ? `${yn(1)} (${x.renewal_term_months || '–'} ${__('months')})` : yn(0)],
    ['Notice period', x.notice_period_days ? `${x.notice_period_days} ${__('days')}` : '–'],
    ['Early termination fee', x.early_termination_fee ? `${x.early_termination_fee} ${x.currency || ''}` : '–'],
    ['Indexation', x.indexation_percent ? `${x.indexation_percent}% / ${x.price_lock_months || 12} ${__('months')}` : '–'],
    ['Included allowance', x.included_allowance ? `${x.included_allowance} ${x.allowance_unit || ''}` : '–'],
    ['Service levels', x.sla_response_hours ? `${x.sla_response_hours} h / ${x.sla_resolution_hours || '–'} h` : '–'],
    ['Visits', x.visit_frequency || '–'],
    ['Signed', x.signed_on ? `${x.signed_by}, ${fmtDate(x.signed_on, true)}` : '–'],
    ['Countersigned', x.countersigned_on ? `${x.countersigned_by}, ${fmtDate(x.countersigned_on, true)}` : '–'],
  ]
})

const errText = (e) => e.messages?.[0] || e.message || __('Something went wrong')
async function load() {
  try {
    c.value = await api('contract.detail', { name: props.name })
  } catch (e) {
    error.value = errText(e)
  }
}
async function act(method) {
  busy.value = true
  error.value = ''
  try {
    await api(method, { name: props.name })
    await load()
  } catch (e) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}
onMounted(load)
</script>
