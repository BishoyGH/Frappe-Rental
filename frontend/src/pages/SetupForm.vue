<template>
  <PageHeader :title="isNew ? __('New {0}', [__(screen.single)]) : rec.title || name" :parent="{ label: __(screen.title), to: { name: screenKey } }">
    <Button variant="solid" :label="__('Save')" :loading="saving" :disabled="!canSave" data-testid="save-record" @click="save" />
  </PageHeader>

  <div class="grid min-h-0 flex-1 overflow-auto lg:grid-cols-[minmax(0,1fr)_280px]">
    <section v-if="loaded" class="min-w-0 p-4" data-testid="setup-form">
      <div v-if="error" class="mb-3 rounded bg-red-50 p-2.5 text-red-700" data-testid="form-error">{{ error }}</div>
      <div v-if="saved" class="mb-3 rounded bg-green-50 p-2.5 text-green-800" data-testid="form-saved">{{ __('Saved') }}</div>

      <template v-for="sec in screen.sections" :key="sec.title">
        <h3 class="mb-2 font-semibold">{{ __(sec.title) }}</h3>
        <div class="mb-5 grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-x-5 gap-y-3">
          <template v-for="f in sec.fields" :key="f.key">
            <label v-if="f.type === 'check'" class="flex items-center gap-2 text-ink-gray-8" :data-testid="`f-${f.key}`">
              <input v-model="checks[f.key]" type="checkbox" /> {{ __(f.label) }}
            </label>
            <div v-else-if="f.type === 'link'">
              <label class="mb-1 block text-sm text-ink-gray-5">{{ __(f.label) }}</label>
              <LinkPicker v-model="form[f.key]" :doctype="f.doctype" :data-testid="`f-${f.key}`" />
            </div>
            <FormControl
              v-else
              v-model="form[f.key]"
              :type="f.type === 'number' ? 'number' : f.type === 'select' ? 'select' : 'text'"
              :label="__(f.label) + (f.reqd ? ' *' : '')"
              :options="f.type === 'select' ? selectOptions(f) : undefined"
              :disabled="f.createOnly && !isNew"
              :data-testid="`f-${f.key}`"
            />
          </template>
        </div>
      </template>

      <template v-if="customMeta.length">
        <h3 class="mb-2 font-semibold">{{ __('Fields of this item type') }}</h3>
        <div class="mb-5 grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] gap-x-5 gap-y-3" data-testid="custom-fields">
          <template v-for="f in customMeta" :key="f.fieldname">
            <label v-if="f.fieldtype === 'Check'" class="flex items-center gap-2"><input v-model="custom[f.fieldname]" type="checkbox" :true-value="1" :false-value="0" /> {{ f.label }}</label>
            <FormControl
              v-else
              v-model="custom[f.fieldname]"
              :type="f.fieldtype === 'Select' ? 'select' : ['Int', 'Float'].includes(f.fieldtype) ? 'number' : f.fieldtype === 'Date' ? 'date' : 'text'"
              :label="f.label + (f.reqd ? ' *' : '')"
              :options="f.fieldtype === 'Select' ? (f.options || '').split('\n').filter(Boolean).map((o) => ({ label: o, value: o })) : undefined"
              :data-testid="`c-${f.fieldname}`"
            />
          </template>
        </div>
      </template>

      <template v-if="screen.customFieldsEditor">
        <h3 class="mb-2 font-semibold">{{ __('Custom fields') }}</h3>
        <p class="mb-2 text-sm text-ink-gray-5">{{ __('Add your own fields to items, units or bookings of this type.') }}</p>
        <div class="grid grid-cols-[130px_minmax(0,1fr)_minmax(0,1fr)_110px_minmax(0,1fr)_50px_32px] items-center gap-2 py-1 text-sm text-ink-gray-5">
          <span>{{ __('Applies to') }}</span><span>{{ __('Label') }}</span><span>{{ __('Field name') }}</span><span>{{ __('Type') }}</span><span>{{ __('Options') }}</span><span>{{ __('Req.') }}</span><span />
        </div>
        <div
          v-for="(row, i) in form.custom_fields"
          :key="i"
          class="grid grid-cols-[130px_minmax(0,1fr)_minmax(0,1fr)_110px_minmax(0,1fr)_50px_32px] items-center gap-2 border-b py-1.5"
          data-testid="cf-row"
        >
          <FormControl v-model="row.applies_to" type="select" :options="(options.applies_to || []).map((o) => ({ label: o, value: o }))" />
          <FormControl v-model="row.label" type="text" data-testid="cf-label" @update:model-value="(v) => autoName(row, v)" />
          <FormControl v-model="row.fieldname" type="text" data-testid="cf-fieldname" @input="row._touched = true" />
          <FormControl v-model="row.fieldtype" type="select" :options="(options.field_types || []).map((o) => ({ label: o, value: o }))" data-testid="cf-type" />
          <FormControl v-model="row.options" type="text" :placeholder="row.fieldtype === 'Select' ? __('One per line, use |') : ''" />
          <input v-model="row.reqd" type="checkbox" :true-value="1" :false-value="0" />
          <Button @click="form.custom_fields.splice(i, 1)"><LucideX class="h-4 w-4" /></Button>
        </div>
        <Button class="mt-2" :label="__('Add field')" data-testid="cf-add" @click="addCustomField"><template #prefix><LucidePlus class="h-4 w-4" /></template></Button>
      </template>
    </section>

    <aside v-if="!isNew" class="border-t bg-surface-gray-1 p-4 lg:border-l lg:border-t-0" data-testid="setup-rail">
      <template v-if="rec.items">
        <h3 class="mb-2 font-semibold">{{ __('Items of this type') }}</h3>
        <RailList :rows="rec.items" label="item_name" route="ItemsForm" />
      </template>
      <template v-if="rec.units">
        <h3 class="mb-2 font-semibold">{{ __('Units') }}</h3>
        <RailList :rows="rec.units" label="unit_name" route="UnitsForm" />
        <Button class="mt-2" :label="__('Add unit')" data-testid="add-unit" @click="router.push({ name: 'UnitsForm', params: { name: 'new' }, query: { rental_item: name } })" />
      </template>
      <template v-if="screen.showBookings">
        <h3 class="mb-2 font-semibold">{{ __('Bookings') }}</h3>
        <div v-for="b in bookings" :key="b.name" class="flex justify-between py-1">
          <router-link :to="{ name: 'BookingDetail', params: { name: b.name } }" class="text-ink-blue-3 hover:underline">{{ b.name }}</router-link>
          <span class="text-ink-gray-5">{{ __(b.status) }}</span>
        </div>
        <p v-if="!bookings.length" class="text-ink-gray-5">{{ __('No bookings yet.') }}</p>
      </template>
    </aside>
  </div>
</template>

<script setup>
import { Button, FormControl } from 'frappe-ui'
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import LucidePlus from '~icons/lucide/plus'
import LucideX from '~icons/lucide/x'
import LinkPicker from '../components/LinkPicker.vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { screens } from '../lib/screens'
import { __ } from '../lib/translate'

const props = defineProps({ screenKey: { type: String, required: true }, name: { type: String, required: true } })
const router = useRouter()
const route = useRoute()
const screen = computed(() => screens[props.screenKey])
const isNew = computed(() => props.name === 'new')
const form = reactive({})
const checks = reactive({})
const custom = reactive({})
const customMeta = ref([])
const options = reactive({})
const rec = ref({})
const bookings = ref([])
const error = ref('')
const saved = ref(false)
const saving = ref(false)
const loaded = ref(false)

const fields = computed(() => screen.value.sections.flatMap((s) => s.fields))
const canSave = computed(() => fields.value.filter((f) => f.reqd).every((f) => form[f.key]))
const selectOptions = (f) => [...(f.blank ? [{ label: '', value: '' }] : []), ...(options[f.options] || []).map((v) => ({ label: __(v), value: v }))]

function reset() {
  for (const k of Object.keys(form)) delete form[k]
  for (const k of Object.keys(checks)) delete checks[k]
  for (const k of Object.keys(custom)) delete custom[k]
  customMeta.value = []
  rec.value = {}
  error.value = ''
  saved.value = false
}

async function load() {
  loaded.value = false
  reset()
  if (isNew.value) {
    Object.assign(form, screen.value.defaults || {}, route.query)
    if (screen.value.customFieldsEditor) form.custom_fields = []
  } else {
    const r = await api('setup.get_record', { doctype: screen.value.doctype, name: props.name })
    rec.value = r
    for (const f of fields.value) (f.type === 'check' ? checks : form)[f.key] = f.type === 'check' ? !!r[f.key] : r[f.key] ?? ''
    if (screen.value.customFieldsEditor) form.custom_fields = r.custom_fields || []
    Object.assign(custom, r.custom)
    customMeta.value = r.custom_meta
    if (screen.value.showBookings) {
      bookings.value = (await api('booking.get_list', { filters: JSON.stringify({ customer: props.name }), page_length: 20 })).rows
    }
  }
  for (const f of fields.value) if (f.type === 'check' && checks[f.key] === undefined) checks[f.key] = !!form[f.key]
  loaded.value = true
}

// New records: show the item type's own fields as soon as the type (or item) is picked
watch(
  () => screen.value.customFrom && form[screen.value.customFrom],
  async (v, old) => {
    if (!screen.value.customFrom || !v || (old === undefined && !isNew.value)) return
    const key = screen.value.customFrom
    try {
      customMeta.value = await api('setup.type_fields', { doctype: screen.value.doctype, [key]: v })
    } catch {
      customMeta.value = []
    }
  },
)

let seq = 0
function addCustomField() {
  form.custom_fields.push({ applies_to: 'Rental Item', label: '', fieldname: '', fieldtype: 'Data', options: '', reqd: 0, _k: ++seq })
}
function autoName(row, label) {
  const auto = (label || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 'f_$1')
  if (!row._touched) row.fieldname = auto
}

async function save() {
  saving.value = true
  error.value = ''
  saved.value = false
  const data = {}
  for (const f of fields.value) {
    if (f.createOnly && !isNew.value) continue
    data[f.key] = f.type === 'check' ? (checks[f.key] ? 1 : 0) : form[f.key] === '' ? null : form[f.key]
  }
  if (screen.value.customFieldsEditor) data.custom_fields = form.custom_fields.map(({ _k, _touched, ...r }) => r)
  if (customMeta.value.length) data.custom = { ...custom }
  try {
    const res = await api('setup.save_record', { doctype: screen.value.doctype, data: JSON.stringify(data), name: isNew.value ? undefined : props.name })
    if (isNew.value) router.replace({ name: `${props.screenKey}Form`, params: { name: res.name } })
    else {
      await load()
      saved.value = true
    }
  } catch (e) {
    error.value = e.messages?.[0] || e.message || __('Could not save')
  } finally {
    saving.value = false
  }
}

watch(() => [props.screenKey, props.name], load)
onMounted(async () => {
  Object.assign(options, await api('setup.form_options'))
  await load()
})

const RailList = defineComponent({
  props: { rows: Array, label: String, route: String },
  setup: (p) => () =>
    p.rows.length
      ? h('div', p.rows.map((r) => h('div', { class: 'py-1' }, h(RouterLink, { to: { name: p.route, params: { name: r.name } }, class: 'text-ink-blue-3 hover:underline' }, () => r[p.label] || r.name))))
      : h('p', { class: 'text-ink-gray-5' }, __('None yet.')),
})
</script>
