<template>
  <PageHeader :title="__('Settings')" />
  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="st-error">{{ error }}</div>
    <div v-if="message" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="st-message">{{ message }}</div>

    <h2 class="mb-2 text-base font-semibold">{{ __('Notifications') }}</h2>
    <p class="mb-3 text-ink-gray-6">
      {{ __('Staff are alerted in the app by role. Turn on email for the roles that should also get a message.') }}
    </p>

    <table class="mb-3 w-full max-w-3xl border-collapse" data-testid="st-rules">
      <thead>
        <tr>
          <th :class="th">{{ __('Event') }}</th>
          <th :class="th">{{ __('Role') }}</th>
          <th :class="th">{{ __('In-app') }}</th>
          <th :class="th">{{ __('Email') }}</th>
          <th v-if="data.can_edit" :class="th" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rules" :key="i" data-testid="st-rule">
          <td :class="td">
            <select v-if="data.can_edit" v-model="r.event" class="rounded border-gray-300 py-1 text-base">
              <option v-for="e in data.events" :key="e" :value="e">{{ eventLabel(e) }}</option>
            </select>
            <span v-else>{{ eventLabel(r.event) }}</span>
          </td>
          <td :class="td">
            <select v-if="data.can_edit" v-model="r.role" class="rounded border-gray-300 py-1 text-base">
              <option v-for="role in data.roles" :key="role" :value="role">{{ role }}</option>
            </select>
            <span v-else>{{ r.role }}</span>
          </td>
          <td :class="td"><input v-model="r.in_app" type="checkbox" :true-value="1" :false-value="0" :disabled="!data.can_edit" /></td>
          <td :class="td"><input v-model="r.email" type="checkbox" :true-value="1" :false-value="0" :disabled="!data.can_edit" /></td>
          <td v-if="data.can_edit" :class="td"><Button variant="ghost" :label="__('Remove')" @click="rules.splice(i, 1)" /></td>
        </tr>
      </tbody>
    </table>
    <div v-if="data.can_edit" class="mb-6 flex gap-2">
      <Button :label="__('Add rule')" data-testid="st-add" @click="add" />
      <Button variant="solid" :label="__('Save')" :loading="saving" data-testid="st-save" @click="save" />
    </div>

    <h2 class="mb-2 text-base font-semibold">{{ __('My alerts') }}</h2>
    <p v-if="!data.alerts.length" class="text-ink-gray-5" data-testid="st-no-alerts">{{ __('No alerts yet.') }}</p>
    <ul v-else class="max-w-3xl divide-y rounded border" data-testid="st-alerts">
      <li v-for="a in data.alerts" :key="a.name" class="flex items-center gap-3 px-3 py-2" :class="a.read ? 'text-ink-gray-5' : 'font-medium'">
        <span class="flex-1">{{ a.subject }}</span>
        <span class="text-ink-gray-5">{{ fmtDate(a.creation, true) }}</span>
        <Button v-if="!a.read" variant="ghost" :label="__('Mark read')" @click="read(a)" />
      </li>
    </ul>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import { onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const th = 'border-b px-2 py-1.5 text-left font-medium text-ink-gray-6'
const td = 'border-b px-2 py-1.5'
const data = ref({ rules: [], events: [], roles: [], alerts: [], can_edit: false })
const rules = ref([])
const error = ref('')
const message = ref('')
const saving = ref(false)

const LABELS = {
  damage_reported: 'Damage reported',
  sla_breached: 'SLA breached',
  housekeeping_overdue: 'Housekeeping overdue',
  overdue: 'Return overdue',
  contract_signed: 'Contract signed',
  contract_notice: 'Contract notice period',
}
const eventLabel = (e) => __(LABELS[e] || e)

async function load() {
  data.value = await api('alerts.get')
  rules.value = data.value.rules.map((r) => ({ ...r }))
}
const add = () => rules.value.push({ event: data.value.events[0], role: data.value.roles[0], in_app: 1, email: 0 })
async function save() {
  saving.value = true
  error.value = message.value = ''
  try {
    await api('alerts.save', { rules: JSON.stringify(rules.value) })
    message.value = __('Saved')
    await load()
  } catch (e) {
    error.value = e.messages?.[0] || e.message
  } finally {
    saving.value = false
  }
}
async function read(a) {
  await api('alerts.mark_read', { name: a.name })
  a.read = 1
}
onMounted(load)
</script>
