<template>
  <PageHeader :title="__(screen.title)">
    <Button v-if="screen.doctype === 'Rental Type'" :label="__('Install presets')" :loading="installing" data-testid="install-presets" @click="installPresets" />
    <Button variant="solid" :label="__('New')" data-testid="new-record" @click="router.push({ name: `${screenKey}Form`, params: { name: 'new' } })">
      <template #prefix><LucidePlus class="h-4 w-4" /></template>
    </Button>
  </PageHeader>
  <div class="flex flex-wrap items-center gap-2 border-b px-4 py-2">
    <FormControl v-model="search" type="text" :placeholder="__('Search')" class="w-56" data-testid="setup-search" />
    <FormControl
      v-for="f in screen.filters || []"
      :key="f.key"
      v-model="filters[f.key]"
      type="select"
      class="w-40"
      :options="[{ label: __(f.label), value: '' }, ...(options[f.options] || []).map((v) => ({ label: __(v), value: v }))]"
    />
  </div>
  <div class="min-w-0 flex-1 overflow-auto px-4 py-3">
    <div v-if="message" class="mb-3 rounded bg-green-50 p-2.5 text-green-800">{{ message }}</div>
    <table class="w-full min-w-[600px] border-collapse" data-testid="setup-table">
      <thead>
        <tr><th v-for="c in screen.columns" :key="c.key" :class="th">{{ __(c.label) }}</th></tr>
      </thead>
      <tbody>
        <tr
          v-for="r in rows"
          :key="r.name"
          class="cursor-pointer hover:bg-surface-gray-1"
          data-testid="setup-row"
          @click="router.push({ name: `${screenKey}Form`, params: { name: r.name } })"
        >
          <td v-for="(c, i) in screen.columns" :key="c.key" :class="[td, i === 0 && 'font-medium text-ink-gray-9']">
            <template v-if="c.check">{{ r[c.key] ? __('Yes') : __('No') }}</template>
            <template v-else>{{ r[c.key] || '-' }}</template>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length">
          <td :colspan="screen.columns.length" class="py-10 text-center text-ink-gray-5">{{ __('Nothing here yet.') }}</td>
        </tr>
      </tbody>
    </table>
    <div class="py-3 text-sm text-ink-gray-5">{{ __('{0} of {1}', [rows.length, total]) }}</div>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import LucidePlus from '~icons/lucide/plus'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { screens } from '../lib/screens'
import { __ } from '../lib/translate'

const props = defineProps({ screenKey: { type: String, required: true } })
const router = useRouter()
const screen = computed(() => screens[props.screenKey])
const th = 'whitespace-nowrap bg-surface-gray-1 px-2.5 py-1.5 text-left text-sm font-medium text-ink-gray-5'
const td = 'whitespace-nowrap border-b px-2.5 py-2 text-ink-gray-7'
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const search = ref('')
const filters = reactive({})
const options = reactive({})
const message = ref('')
const installing = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await api('setup.get_records', {
      doctype: screen.value.doctype,
      search: search.value || undefined,
      filters: JSON.stringify(filters),
      page_length: 200,
    })
    rows.value = res.rows
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function installPresets() {
  installing.value = true
  try {
    const added = await api('setup.install_presets')
    message.value = added.length ? __('Added presets: {0}', [added.join(', ')]) : __('All presets are already installed.')
    load()
  } finally {
    installing.value = false
  }
}

let timer
watch([search, filters], () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
watch(() => props.screenKey, () => { search.value = ''; Object.keys(filters).forEach((k) => delete filters[k]); load() })
onMounted(async () => {
  load()
  if (screen.value.filters) Object.assign(options, await api('setup.form_options'))
})
</script>
