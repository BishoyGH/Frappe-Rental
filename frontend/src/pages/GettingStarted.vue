<template>
  <PageHeader :title="__('Getting started')" />
  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="gs-error">{{ error }}</div>
    <template v-if="data">
      <h2 class="mb-1 text-base font-semibold">{{ data.title }}</h2>
      <p class="mb-3 text-ink-gray-6" data-testid="gs-progress">
        {{ __('{0} of {1} steps done', [data.done, data.total]) }}
      </p>
      <p v-if="data.total && data.done === data.total" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="gs-complete">
        {{ __('The Rental module is all set up!') }}
      </p>
      <ol class="max-w-xl divide-y rounded border" data-testid="gs-steps">
        <li v-for="s in data.steps" :key="s.name" class="flex items-center gap-3 px-3 py-2.5" data-testid="gs-step">
          <span
            class="grid h-5 w-5 place-items-center rounded-full border text-xs"
            :class="s.done ? 'border-green-600 bg-green-600 text-white' : 'text-ink-gray-5'"
          >{{ s.done ? '✓' : '' }}</span>
          <span class="flex-1" :class="s.done ? 'text-ink-gray-5 line-through' : ''">{{ s.title }}</span>
          <a v-if="!s.done" :href="newUrl(s.doctype)" class="text-ink-blue-3 hover:underline">{{ __('Start') }}</a>
        </li>
      </ol>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { __ } from '../lib/translate'

const data = ref(null)
const error = ref('')
const newUrl = (dt) => `/app/${dt.toLowerCase().replaceAll(' ', '-')}/new`
onMounted(async () => {
  try {
    data.value = await api('alerts.onboarding')
  } catch (e) {
    error.value = e.message
  }
})
</script>
