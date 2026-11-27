<template>
  <PageHeader :title="name" :parent="{ label: __('Bookings'), to: { name: 'Bookings' } }">
    <template #title-extra><StatusBadge v-if="b" :status="b.status" /></template>
    <template v-if="b">
      <Button v-if="can('cancel')" :label="b.status === 'Hold' ? __('Release hold') : __('Cancel')" :loading="busy === 'cancel'" data-testid="action-cancel" @click="act('cancel', 'booking.cancel')" />
      <Button v-if="can('hold')" :label="__('Hold')" :loading="busy === 'hold'" data-testid="action-hold" @click="act('hold', 'booking.create_hold')" />
      <Button v-if="can('invoice')" :label="__('Create invoice')" :loading="busy === 'invoice'" data-testid="action-invoice" @click="act('invoice', 'booking.make_invoice')" />
      <Button v-if="can('confirm')" variant="solid" :label="__('Confirm')" :loading="busy === 'confirm'" data-testid="action-confirm" @click="act('confirm', 'booking.confirm')" />
    </template>
  </PageHeader>

  <div v-if="error" class="m-4 rounded bg-surface-red-1 p-3 text-ink-red-4" data-testid="error">{{ error }}</div>

  <template v-if="b">
    <nav class="flex gap-4 border-b px-4" data-testid="tabs">
      <button
        v-for="t in TABS"
        :key="t"
        class="py-2.5 text-base"
        :class="tab === t ? 'font-medium text-ink-gray-9 shadow-[inset_0_-2px_0_theme(colors.gray.900)]' : 'text-ink-gray-5'"
        @click="tab = t"
      >
        {{ __(t) }}
      </button>
    </nav>

    <div class="grid min-h-0 flex-1 overflow-auto lg:grid-cols-[minmax(0,1fr)_280px]">
      <section class="min-w-0 p-4">
        <template v-if="tab === 'Overview'">
          <div class="mb-5 grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-x-5 gap-y-3">
            <Field :label="__('Customer')" :value="b.customer_name" />
            <Field :label="__('Item type')" :value="b.rental_type" />
            <Field :label="__('Location')" :value="b.location" />
            <Field :label="__('From')" :value="fmtDate(b.from_datetime, true)" />
            <Field :label="__('To')" :value="fmtDate(b.to_datetime, true)" />
            <Field v-if="b.status === 'Hold'" :label="__('Hold expires')" :value="fmtDate(b.hold_expires_on, true)" />
            <Field :label="__('Source')" :value="b.source" />
          </div>
          <LinesTable :lines="b.lines" :charges="b.charges" />
        </template>
        <LinesTable v-else-if="tab === 'Items'" :lines="b.lines" :charges="b.charges" />
        <BillingTab v-else-if="tab === 'Billing'" :name="name" />
        <DepositDamageTab v-else-if="tab === 'Deposit & damage'" :name="name" @changed="load" />
        <template v-else-if="tab === 'Documents'">
          <LinkList :links="b.links" />
        </template>
        <div v-else data-testid="handover-tab">
          <p class="mb-3 text-ink-gray-6">{{ __('Hand units out and take them back on the Handovers screen.') }}</p>
          <Button variant="solid" :label="__('Open handover')" data-testid="open-handover" @click="router.push({ name: 'Handovers', query: { booking: name } })" />
        </div>
      </section>

      <aside class="border-t bg-surface-gray-1 p-4 lg:border-s lg:border-t-0" data-testid="side-panel">
        <h3 class="mb-2 font-semibold">{{ __('Summary') }}</h3>
        <Kv :label="__('Net')" :value="money(b.net_total)" />
        <Kv :label="b.taxes_and_charges || __('Taxes')" :value="money(b.total_taxes)" />
        <Kv :label="__('Total {0}', [b.currency || ''])" :value="money(b.grand_total)" strong data-testid="grand-total" />

        <h3 class="mb-2 mt-5 font-semibold">{{ __('Deposit') }}</h3>
        <Kv :label="__('Required')" :value="money(b.deposit_required)" />
        <div class="flex justify-between py-1">
          <span class="text-ink-gray-5">{{ __('Held') }}</span>
          <Badge v-if="!b.deposit_required" :label="__('Not needed')" theme="gray" />
          <Badge v-else-if="b.deposit_paid >= b.deposit_required" :label="__('Paid')" theme="green" />
          <Badge v-else :label="__('Due')" theme="orange" />
        </div>

        <h3 class="mb-2 mt-5 font-semibold">{{ __('Linked') }}</h3>
        <LinkList :links="b.links" />

        <h3 class="mb-2 mt-5 font-semibold">{{ __('Activity') }}</h3>
        <div v-for="(e, i) in b.activity" :key="i" class="flex gap-2.5 py-1.5 text-ink-gray-7" data-testid="activity">
          <i class="mt-1.5 h-1.5 w-1.5 flex-none rounded-full bg-gray-400" />
          <div>{{ e.text }}<small class="block text-ink-gray-5">{{ fromNow(e.at, b.server_now) }}</small></div>
        </div>
      </aside>
    </div>
  </template>
</template>

<script setup>
import { Badge, Button } from 'frappe-ui'
import { defineComponent, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BillingTab from '../components/BillingTab.vue'
import DepositDamageTab from '../components/DepositDamageTab.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate, fmtMoney, fromNow } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true } })
const TABS = ['Overview', 'Items', 'Billing', 'Deposit & damage', 'Documents', 'Handover']
const router = useRouter()
const tab = ref('Overview')
const b = ref(null)
const error = ref('')
const busy = ref('')

const money = (v) => fmtMoney(v)
const can = (a) => b.value?.actions?.includes(a)

async function load() {
  error.value = ''
  try {
    b.value = await api('booking.get_detail', { name: props.name })
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not load booking')
  }
}

async function act(key, method) {
  busy.value = key
  error.value = ''
  try {
    await api(method, { name: props.name })
    await load()
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Action failed')
  } finally {
    busy.value = ''
  }
}

watch(() => props.name, load)
onMounted(load)

const Field = defineComponent({
  props: { label: String, value: [String, Number] },
  setup: (p) => () =>
    h('div', [
      h('label', { class: 'mb-1 block text-sm text-ink-gray-5' }, p.label),
      h('div', { class: 'flex h-7 items-center rounded bg-surface-gray-2 px-2 text-ink-gray-9' }, p.value || '-'),
    ]),
})

const Kv = defineComponent({
  props: { label: String, value: [String, Number], strong: Boolean },
  setup: (p, { attrs }) => () =>
    h(
      'div',
      {
        ...attrs,
        class: ['flex justify-between gap-2 py-1', p.strong && 'mt-1 border-t pt-2 font-semibold text-ink-gray-9'],
      },
      [h('span', { class: p.strong ? '' : 'text-ink-gray-5' }, p.label), h('span', { class: 'tabular-nums' }, p.value)],
    ),
})

const LinkList = defineComponent({
  props: { links: Array },
  setup: (p) => () =>
    p.links?.length
      ? h(
          'div',
          p.links.map((l) =>
            h('div', { class: 'flex justify-between py-1', 'data-testid': 'linked-doc' }, [
              h('span', { class: 'whitespace-nowrap text-ink-gray-5' }, __(l.doctype)),
              h(
                'a',
                { href: `/app/${l.doctype.toLowerCase().replaceAll(' ', '-')}/${l.name}`, class: 'text-ink-blue-3 hover:underline' },
                l.name,
              ),
            ]),
          ),
        )
      : h('p', { class: 'text-ink-gray-5' }, __('Nothing linked yet.')),
})

const LinesTable = defineComponent({
  props: { lines: Array, charges: Array },
  setup: (p) => {
    const th = 'bg-surface-gray-1 px-2.5 py-1.5 text-start text-sm font-medium text-ink-gray-5 whitespace-nowrap'
    const td = 'border-b px-2.5 py-2 text-ink-gray-7 whitespace-nowrap'
    const num = ' text-end tabular-nums'
    return () =>
      h('div', { class: 'overflow-x-auto' }, [
        h('h3', { class: 'mb-2 font-semibold' }, __('Items')),
        h('table', { class: 'w-full min-w-[560px] border-collapse', 'data-testid': 'lines' }, [
          h('thead', h('tr', [__('Item'), __('Unit'), __('Qty'), __('Basis'), __('Rate'), __('Amount')].map((t, i) => h('th', { class: th + (i === 2 || i > 3 ? num : '') }, t)))),
          h('tbody', [
            ...p.lines.map((l) =>
              h('tr', [
                h('td', { class: td }, l.item_name),
                h('td', { class: td }, l.unit_name || '-'),
                h('td', { class: td + num }, l.qty),
                h('td', { class: td }, l.units ? `${l.units} × ${__(l.time_unit)}` : __(l.time_unit || '')),
                h('td', { class: td + num }, fmtMoney(l.rate)),
                h('td', { class: td + num }, fmtMoney(l.amount)),
              ]),
            ),
            ...p.charges.map((c) =>
              h('tr', [
                h('td', { class: td }, c.description || c.charge),
                h('td', { class: td }, '-'),
                h('td', { class: td + num }, 1),
                h('td', { class: td }, __('Fixed')),
                h('td', { class: td + num }, fmtMoney(c.amount)),
                h('td', { class: td + num }, fmtMoney(c.amount)),
              ]),
            ),
          ]),
        ]),
      ])
  },
})
</script>
