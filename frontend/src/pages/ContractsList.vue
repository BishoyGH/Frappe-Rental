<template>
  <PageHeader :title="__('Contracts')" />
  <div class="flex flex-wrap items-center gap-2 border-b px-4 py-2" data-testid="filters">
    <FormControl v-model="search" type="text" :placeholder="__('Search contract or customer')" class="w-60" data-testid="ct-search" />
    <FormControl v-model="status" type="select" :options="statusOptions" class="w-44" data-testid="ct-status" />
  </div>
  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="rounded bg-surface-red-1 p-3 text-ink-red-4">{{ error }}</div>
    <table v-else class="w-full min-w-[640px] border-collapse" data-testid="contracts-table">
      <thead>
        <tr>
          <th v-for="h in heads" :key="h" class="bg-surface-gray-1 px-2.5 py-1.5 text-left text-sm font-medium text-ink-gray-5">{{ __(h) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.name" class="cursor-pointer hover:bg-surface-gray-1" data-testid="ct-row" @click="open(r.name)">
          <td class="border-b px-2.5 py-2 font-medium">{{ r.name }}</td>
          <td class="border-b px-2.5 py-2">{{ r.customer_name }}</td>
          <td class="border-b px-2.5 py-2"><StatusBadge :status="r.status" /></td>
          <td class="border-b px-2.5 py-2 text-ink-gray-6">{{ fmtDate(r.start_date) }} → {{ r.open_ended ? __('open-ended') : fmtDate(r.end_date) }}</td>
          <td class="border-b px-2.5 py-2 text-ink-gray-6">{{ r.signed_on ? fmtDate(r.signed_on) : '–' }}</td>
        </tr>
        <tr v-if="loaded && !rows.length"><td colspan="5" class="px-2.5 py-6 text-center text-ink-gray-5">{{ __('No contracts.') }}</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { FormControl } from 'frappe-ui'
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const STATUSES = ['Draft', 'In Review', 'Awaiting Signature', 'Active', 'Suspended', 'Ending', 'Ended', 'Terminated', 'Renewed']
const heads = ['Contract', 'Customer', 'Status', 'Term', 'Signed']
const statusOptions = [{ label: __('Status: any'), value: '' }, ...STATUSES.map((s) => ({ label: __(s), value: s }))]
const router = useRouter()
const rows = ref([])
const search = ref('')
const status = ref('')
const error = ref('')
const loaded = ref(false)
let timer

async function load() {
  try {
    rows.value = (await api('contract.listing', { status: status.value, search: search.value })).rows
    error.value = ''
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  } finally {
    loaded.value = true
  }
}
const open = (name) => router.push({ name: 'ContractDetail', params: { name } })
watch([search, status], () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(load)
</script>
