<template>
  <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="dd-error">{{ error }}</div>
  <template v-if="data">
    <h3 class="mb-2 font-semibold">{{ __('Deposit') }}</h3>
    <div v-if="!data.deposit" class="mb-4 text-ink-gray-5" data-testid="dep-none">{{ __('No deposit on this booking.') }}</div>
    <div v-else class="mb-5" data-testid="dep-panel">
      <div class="mb-2 flex items-center gap-2">
        <span class="font-medium">{{ data.deposit.name }}</span><Badge :label="__(data.deposit.status)" theme="blue" />
      </div>
      <div class="grid max-w-xl grid-cols-2 gap-x-6 gap-y-1">
        <span class="text-ink-gray-5">{{ __('Required') }}</span><span class="tabular-nums">{{ fmtMoney(data.deposit.amount_required) }}</span>
        <span class="text-ink-gray-5">{{ __('Received') }}</span><span class="tabular-nums">{{ fmtMoney(data.deposit.amount_received) }}</span>
        <span class="text-ink-gray-5">{{ __('Held') }}</span><span class="tabular-nums font-semibold" data-testid="dep-held">{{ fmtMoney(data.deposit.balance_held) }}</span>
        <span class="text-ink-gray-5">{{ __('Applied / refunded / kept') }}</span>
        <span class="tabular-nums">{{ fmtMoney(data.deposit.amount_applied) }} / {{ fmtMoney(data.deposit.amount_refunded) }} / {{ fmtMoney(data.deposit.amount_forfeited) }}</span>
      </div>
      <div class="mt-3 flex flex-wrap items-end gap-2">
        <FormControl v-model="amount" type="number" :label="__('Amount')" class="w-32" data-testid="dep-amount" />
        <Button :label="__('Collect')" :loading="busy === 'collect'" data-testid="dep-collect" @click="deposit('collect')" />
        <Button :label="__('Refund')" :disabled="!data.deposit.balance_held" :loading="busy === 'refund'" data-testid="dep-refund" @click="deposit('refund')" />
        <Button :label="__('Keep')" :disabled="!data.deposit.balance_held" :loading="busy === 'forfeit'" @click="deposit('forfeit')" />
      </div>
      <div v-for="(e, i) in data.deposit.entries" :key="i" class="mt-1 flex gap-3 text-ink-gray-6" data-testid="dep-entry">
        <span class="w-20">{{ __(e.action) }}</span><span class="tabular-nums">{{ fmtMoney(e.amount) }}</span><span>{{ fmtDate(e.posting_date) }}</span>
        <a v-if="e.journal_entry" :href="`/app/journal-entry/${e.journal_entry}`" class="text-ink-blue-3 hover:underline">{{ e.journal_entry }}</a>
      </div>
    </div>

    <h3 class="mb-2 font-semibold">{{ __('Damage') }}</h3>
    <p v-if="!data.damages.length" class="text-ink-gray-5" data-testid="dmg-none">{{ __('No damage reported.') }}</p>
    <div v-for="d in data.damages" :key="d.name" class="mb-3 rounded border p-3" data-testid="dmg-report">
      <div class="mb-1 flex items-center gap-2">
        <a :href="`/app/rental-damage-report/${d.name}`" class="font-medium hover:underline">{{ d.name }}</a>
        <Badge :label="__(d.status)" :theme="d.status === 'Settled' || d.status === 'Written Off' ? 'green' : 'orange'" data-testid="dmg-status" />
        <span class="text-ink-gray-5">{{ d.rental_unit }}</span>
      </div>
      <p class="text-ink-gray-7">{{ d.description }}</p>
      <div v-if="!['Settled', 'Written Off'].includes(d.status)" class="mt-2 flex flex-wrap items-end gap-2">
        <template v-if="d.status !== 'Approved'">
          <FormControl v-model="approve[d.name]" type="number" :label="__('Approved amount')" class="w-36" :data-testid="`dmg-amount-${d.name}`" />
          <Button :label="__('Approve')" :loading="busy === d.name" data-testid="dmg-approve" @click="approveDamage(d)" />
        </template>
        <template v-else>
          <span class="text-ink-gray-6">{{ __('Approved {0}', [fmtMoney(d.approved_amount)]) }}</span>
          <Button :label="__('From deposit')" :disabled="!data.deposit" data-testid="dmg-deposit" @click="settle(d, 'Deposit')" />
          <Button :label="__('Invoice')" data-testid="dmg-invoice" @click="settle(d, 'Invoice')" />
        </template>
        <Button :label="__('Write off')" data-testid="dmg-writeoff" @click="settle(d, 'Write-off')" />
      </div>
    </div>
  </template>
</template>

<script setup>
import { Badge, Button, FormControl } from 'frappe-ui'
import { onMounted, reactive, ref } from 'vue'
import { api } from '../lib/api'
import { fmtDate, fmtMoney } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(['changed'])
const data = ref(null)
const error = ref('')
const busy = ref('')
const amount = ref('')
const approve = reactive({})

const fail = (e) => (error.value = e.messages?.[0] || e.message || __('Action failed'))

async function load() {
  try {
    data.value = await api('ops.panels', { name: props.name })
    for (const d of data.value.damages) approve[d.name] ??= d.estimate_amount || ''
  } catch (e) {
    fail(e)
  }
}

async function run(key, fn) {
  busy.value = key
  error.value = ''
  try {
    await fn()
    await load()
    emit('changed')
  } catch (e) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

const deposit = (action) =>
  run(action, () =>
    action === 'collect'
      ? api('deposit.collect', { deposit: data.value.deposit.name, amount: amount.value || data.value.deposit.amount_required - data.value.deposit.amount_received })
      : api('deposit.settle', { deposit: data.value.deposit.name, action, amount: amount.value || null }),
  )
const approveDamage = (d) => run(d.name, () => api('ops.approve_damage', { name: d.name, amount: approve[d.name] }))
const settle = (d, method) => run(d.name, () => api('ops.settle_damage', { name: d.name, method }))

onMounted(load)
</script>
