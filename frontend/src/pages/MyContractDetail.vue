<template>
  <div class="mx-auto max-w-3xl px-4 py-6" data-testid="mc-detail">
    <router-link :to="{ name: 'MyContracts' }" class="text-sm text-ink-blue-3 hover:underline">← {{ __('My contracts') }}</router-link>
    <div v-if="error" class="my-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="mc-error">{{ error }}</div>
    <div v-if="message" class="my-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="mc-message">{{ message }}</div>

    <template v-if="c">
      <div class="my-3 flex flex-wrap items-center gap-3">
        <h1 class="text-xl font-semibold" data-testid="mc-name">{{ c.name }}</h1>
        <StatusBadge :status="c.status" />
        <span class="text-ink-gray-5">{{ fmtDate(c.start_date) }} → {{ c.open_ended ? __('open-ended') : fmtDate(c.end_date) }}</span>
      </div>

      <section v-if="c.terms_html" class="mb-4">
        <h2 class="mb-2 font-semibold">{{ __('Terms') }}</h2>
        <div class="prose max-h-96 overflow-auto rounded border p-3" data-testid="mc-terms" v-html="c.terms_html" />
      </section>

      <section v-if="c.awaiting_signature && c.can_sign" class="mb-4" data-testid="mc-sign">
        <h2 class="mb-2 font-semibold">{{ __('Sign this contract') }}</h2>
        <div class="space-y-2">
          <FormControl v-model="signer" type="text" :label="__('Type your full name to sign')" data-testid="mc-signer" />
          <template v-if="c.require_otp">
            <FormControl v-model="otp" type="text" :label="__('Signing code from your email')" data-testid="mc-otp" />
            <Button :label="__('Email me a code')" :loading="busy" data-testid="mc-send-otp" @click="run(() => api('contract.request_otp', { name }), __('Code sent'))" />
          </template>
          <Button variant="solid" :label="__('Sign')" :loading="busy" data-testid="mc-sign-btn" @click="sign" />
        </div>
      </section>
      <p v-else-if="c.signed && c.status === 'Awaiting Signature'" class="mb-4 text-ink-gray-6" data-testid="mc-signed">{{ __('You signed. We will countersign shortly.') }}</p>

      <section v-if="c.allocations.length" class="mb-4">
        <h2 class="mb-2 font-semibold">{{ __('What is covered') }}</h2>
        <div v-for="a in c.allocations" :key="a.name" class="border-b py-1.5">{{ a.rental_unit || a.rental_item }} · {{ fmtDate(a.from_date) }} → {{ fmtDate(a.to_date) }}</div>
      </section>

      <section v-if="c.can_request_service || c.visits.length" class="mb-4" data-testid="mc-visits">
        <h2 class="mb-2 font-semibold">{{ __('Visits and service') }}</h2>
        <div v-for="(v, i) in c.visits" :key="i" class="flex items-center justify-between border-b py-1.5">
          <span>{{ fmtDate(v.planned_date) }} · {{ v.visit_type }}<span v-if="v.notes" class="text-ink-gray-5"> – {{ v.notes }}</span></span>
          <StatusBadge :status="v.status" />
        </div>
        <div v-if="c.can_request_service" class="mt-3 flex items-end gap-2">
          <FormControl v-model="problem" type="text" :label="__('Need a visit? Describe the problem')" class="flex-1" data-testid="mc-problem" />
          <Button :label="__('Request service')" :loading="busy" data-testid="mc-request" @click="request" />
        </div>
      </section>

      <a v-if="c.has_pdf" :href="pdfUrl" class="text-ink-blue-3 hover:underline" data-testid="mc-pdf">{{ __('Download signed contract') }}</a>
    </template>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../lib/api'
import { fmtDate } from '../lib/format'
import { __ } from '../lib/translate'

const props = defineProps({ name: { type: String, required: true } })
const c = ref(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const signer = ref('')
const otp = ref('')
const problem = ref('')
const pdfUrl = `/api/method/frappe_rental.api.portal.download_contract?name=${encodeURIComponent(props.name)}`

const errText = (e) => e.messages?.[0] || e.message || __('Something went wrong')
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
const load = async () => (c.value = await api('contract.my_contract', { name: props.name }))
const sign = () =>
  run(async () => {
    await api('contract.sign', { name: props.name, signer_name: signer.value, signature: signer.value, ...(otp.value ? { otp: otp.value } : {}) })
    await load()
  }, __('Thank you. Your signature is recorded.'))
const request = () =>
  run(async () => {
    await api('contract.request_service', { name: props.name, notes: problem.value })
    problem.value = ''
    await load()
  }, __('Request sent. We will be in touch.'))

onMounted(() => run(load))
</script>
