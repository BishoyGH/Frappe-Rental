<template>
  <div class="relative">
    <FormControl
      :model-value="text"
      type="text"
      :placeholder="placeholder"
      autocomplete="off"
      v-bind="$attrs"
      @update:model-value="onInput"
      @focus="open = true; search(text)"
      @blur="close"
    />
    <ul
      v-if="open && results.length"
      class="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border bg-surface-white p-1 shadow-lg"
      role="listbox"
    >
      <li
        v-for="r in results"
        :key="r.value"
        role="option"
        class="cursor-pointer rounded px-2 py-1.5 hover:bg-surface-gray-2"
        @mousedown.prevent="pick(r)"
      >
        {{ r.label }} <span v-if="r.label !== r.value" class="text-ink-gray-5">{{ r.value }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { FormControl } from 'frappe-ui'
import { ref, watch } from 'vue'
import { api } from '../lib/api'

defineOptions({ inheritAttrs: false })
const props = defineProps({ doctype: String, modelValue: String, placeholder: String, rentalItem: String })
const emit = defineEmits(['update:modelValue'])
const text = ref(props.modelValue || '')
let picked = props.modelValue || ''
const results = ref([])
const open = ref(false)
let timer

async function search(txt) {
  try {
    results.value = await api('booking.search_link', { doctype: props.doctype, txt, rental_item: props.rentalItem })
  } catch {
    results.value = []
  }
}
function onInput(v) {
  if (v === text.value) return // change/blur re-emits the same text
  text.value = v
  open.value = true
  emit('update:modelValue', '')
  clearTimeout(timer)
  timer = setTimeout(() => search(v), 200)
}
function pick(r) {
  text.value = r.label
  picked = r.value
  open.value = false
  emit('update:modelValue', r.value)
}
function close() {
  setTimeout(() => (open.value = false), 100)
}
watch(
  () => props.modelValue,
  (v) => {
    if (v && v !== picked) {
      picked = v
      text.value = v
    }
  },
)
watch(
  () => props.rentalItem,
  () => {
    text.value = ''
    emit('update:modelValue', '')
  },
)
</script>
