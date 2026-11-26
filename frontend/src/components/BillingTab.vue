<template>
  <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="bill-error">{{ error }}</div>
  <div v-if="saved" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="bill-saved">{{ __('Schedule saved') }}</div>
  <template v-if="bill">
    <p class="mb-2 text-ink-gray-6">
      {{ __('Plan') }}: <b>{{ bill.plan ? __(bill.plan.frequency || 'Custom') : __('One-off') }}</b>
      · {{ __('Invoiced') }} {{ fmtMoney(bill.invoiced) }} · {{ __('Planned') }} {{ fmtMoney(bill.planned) }}
    </p>
    <div class="overflow-x-auto">
      <table class="w-full min-w-[720px] border-collapse" data-testid="bill-rows">
        <thead>
          <tr>
            <th v-for="h in HEAD" :key="h" :class="th">{{ __(h) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.idx" data-testid="bill-row">
            <td :class="td">{{ fmtDate(r.period_from) }} → {{ fmtDate(r.period_to) }}</td>
            <td :class="td">
              <input v-if="r.editable" v-model="r.invoice_date" type="date" class="rounded border-gray-300 py-1 text-base" :data-testid="`bill-date-${r.idx}`" />
              <span v-else>{{ fmtDate(r.invoice_date) }}</span>
            </td>
            <td :class="[td, 'text-right']">
              <input v-if="r.editable" v-model.number="r.amount" type="number" step="0.01" class="w-28 rounded border-gray-300 py-1 text-right text-base" :data-testid="`bill-amount-${r.idx}`" />
              <span v-else class="tabular-nums">{{ fmtMoney(r.amount) }}</span>
            </td>
            <td :class="td"><Badge :label="__(r.status)" :theme="r.editable ? 'gray' : 'green'" /></td>
            <td :class="td">
              <a v-if="r.sales_invoice" :href="`/app/sales-invoice/${r.sales_invoice}`" class="text-ink-blue-3 hover:underline">{{ r.sales_invoice }}</a>
            </td>
            <td :class="td">
              <input v-if="r.editable" v-model="r.adjustment_note" class="w-full rounded border-gray-300 py-1 text-base" />
              <span v-else>{{ r.adjustment_note }}</span>
            </td>
          </tr>
          <tr>
            <td :class="[td, 'font-semibold']" colspan="2">{{ __('Total') }}</td>
            <td :class="[td, 'text-right font-semibold tabular-nums']" :data-testid="'bill-total'">{{ fmtMoney(total) }}</td>
            <td :class="td" colspan="3">
              <span v-if="Math.abs(total - bill.net_total) > 0.005" class="text-red-600">{{ __('Must equal {0}', [fmtMoney(bill.net_total)]) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Button v-if="rows.some((r) => r.editable)" class="mt-3" variant="solid" :label="__('Save schedule')" :loading="busy" :disabled="!canWrite" data-testid="bill-save" @click="save" />
  </template>
</template>

<script setup>
import { Badge, Button } from 'frappe-ui'
import { computed, onMounted, ref } from 'vue'
import { api } from '../lib/api'
import { fmtDate, fmtMoney } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true }, canWrite: { type: Boolean, default: true } })
const HEAD = ['Period', 'Invoice date', 'Amount', 'Status', 'Invoice', 'Note']
const th = 'bg-surface-gray-1 px-2.5 py-1.5 text-left text-sm font-medium text-ink-gray-5 whitespace-nowrap'
const td = 'border-b px-2.5 py-2 text-ink-gray-7 whitespace-nowrap'
const bill = ref(null)
const rows = ref([])
const error = ref('')
const saved = ref(false)
const busy = ref(false)
const total = computed(() => rows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0))

async function load() {
  try {
    bill.value = await api('ops.billing', { name: props.name })
    rows.value = bill.value.rows.map((r) => ({ ...r }))
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  }
}

async function save() {
  busy.value = true
  error.value = ''
  saved.value = false
  try {
    const edits = rows.value.filter((r) => r.editable).map(({ idx, invoice_date, amount, adjustment_note }) => ({ idx, invoice_date, amount, adjustment_note }))
    bill.value = await api('ops.save_schedule', { name: props.name, rows: JSON.stringify(edits) })
    rows.value = bill.value.rows.map((r) => ({ ...r }))
    saved.value = true
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
