<template>
  <PageHeader :title="__('Calendar')">
    <Button :label="__('Today')" @click="goto(startOfDay(new Date()))" />
    <Button :tooltip="__('Previous')" data-testid="prev" @click="goto(addDays(start, -DAYS))"><LucideChevronLeft class="h-4 w-4" /></Button>
    <Button :tooltip="__('Next')" data-testid="next" @click="goto(addDays(start, DAYS))"><LucideChevronRight class="h-4 w-4" /></Button>
    <Button variant="solid" :label="__('New booking')" @click="router.push({ name: 'BookingNew' })">
      <template #prefix><LucidePlus class="h-4 w-4" /></template>
    </Button>
  </PageHeader>

  <div class="flex flex-wrap items-center gap-2 border-b px-4 py-2">
    <FormControl v-model="location" type="select" :options="opt(options.locations, __('Location: all'))" class="w-40" />
    <FormControl v-model="rentalType" type="select" :options="opt(options.rental_types, __('Type: all'))" class="w-40" data-testid="cal-type" />
    <FormControl v-model="startInput" type="date" class="w-40" data-testid="cal-start" />
    <span class="text-sm text-ink-gray-5">{{ __('Drag across empty days to book. Drag a draft or held booking to move it.') }}</span>
  </div>

  <div v-if="message" class="mx-4 mt-3 rounded p-2.5" :class="message.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-700'" data-testid="cal-message">
    {{ message.text }}
  </div>

  <div class="min-w-0 flex-1 overflow-auto px-4 py-3 select-none" @mouseup="endSelect">
    <div class="grid min-w-[760px]" :style="{ gridTemplateColumns: `160px repeat(${DAYS}, minmax(40px, 1fr))` }" data-testid="timeline">
      <div />
      <div v-for="(d, i) in days" :key="i" class="py-1.5 text-center text-xs tabular-nums" :class="isToday(d) ? 'font-semibold text-ink-blue-3' : 'text-ink-gray-5'">
        {{ d.getDate() }}<br />{{ d.toLocaleDateString(undefined, { weekday: 'short' }) }}
      </div>

      <template v-for="u in units" :key="u.name">
        <div class="truncate border-t px-2 py-2 font-medium text-ink-gray-8" data-testid="cal-row" :data-unit="u.name">
          {{ u.unit_name }}<small class="block truncate font-normal text-ink-gray-5">{{ u.item_name }}</small>
        </div>
        <div class="relative col-span-full col-start-2 grid border-t" :style="{ gridTemplateColumns: `repeat(${DAYS}, minmax(40px, 1fr))` }">
          <div
            v-for="(d, i) in days"
            :key="i"
            class="min-h-[44px] border-l"
            :class="inSelection(u, i) ? 'bg-blue-50' : dragOver === `${u.name}|${i}` ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-1'"
            data-testid="cal-cell"
            :data-unit="u.name"
            :data-day="i"
            @mousedown="beginSelect(u, i)"
            @mouseenter="extendSelect(u, i)"
            @dragover.prevent="dragOver = `${u.name}|${i}`"
            @dragleave="dragOver = ''"
            @drop.prevent="drop(u, i)"
          />
          <div
            v-for="e in u.events"
            :key="e.kind + e.name"
            class="absolute bottom-1.5 top-1.5 z-10 truncate rounded-md px-1.5 py-0.5 text-xs font-medium"
            :class="[EVENT_CLASS[e.status] || EVENT_CLASS.Draft, e.movable ? 'cursor-grab' : 'cursor-pointer', dragging && dragging.event !== e && 'pointer-events-none']"
            :style="barStyle(e)"
            :draggable="e.movable"
            :title="`${e.label} · ${e.name}`"
            data-testid="cal-event"
            :data-name="e.name"
            @dragstart="dragging = { event: e, unit: u }"
            @dragend="dragging = null; dragOver = ''"
            @mousedown.stop
            @click="e.kind === 'booking' && router.push({ name: 'BookingDetail', params: { name: e.name } })"
          >
            {{ e.label }}
          </div>
        </div>
      </template>
    </div>
    <p v-if="!loading && !units.length" class="py-10 text-center text-ink-gray-5">{{ __('No units match these filters.') }}</p>

    <div class="mt-3 flex flex-wrap gap-1.5">
      <Badge v-for="(cls, s) in LEGEND" :key="s" :label="__(s)" :theme="cls" />
    </div>
  </div>

  <QuickBook
    v-if="quick"
    v-bind="quick"
    @close="quick = null"
    @booked="(name) => { quick = null; flash(__('Booking {0} held', [name]), true); load() }"
  />
</template>

<script setup>
import { Badge, Button, FormControl } from 'frappe-ui'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import LucideChevronLeft from '~icons/lucide/chevron-left'
import LucideChevronRight from '~icons/lucide/chevron-right'
import LucidePlus from '~icons/lucide/plus'
import PageHeader from '../components/PageHeader.vue'
import QuickBook from '../components/QuickBook.vue'
import { api } from '../lib/api'
import { addDays, parseDt, startOfDay, toDt } from '../lib/format'
import { __ } from '../lib/translate'

const DAYS = 14
const DAY_MS = 86400000
const EVENT_CLASS = {
  Draft: 'bg-gray-200 text-gray-700',
  Hold: 'bg-amber-100 text-amber-800',
  Confirmed: 'bg-blue-100 text-blue-800',
  'Checked Out': 'bg-violet-100 text-violet-800',
  Returned: 'bg-green-100 text-green-800',
  Closed: 'bg-green-100 text-green-800',
  Blocked: 'bg-red-100 text-red-800',
}
const LEGEND = { Draft: 'gray', Hold: 'orange', Confirmed: 'blue', Returned: 'green', Blocked: 'red' }

const router = useRouter()
const start = ref(startOfDay(new Date()))
const startInput = computed({
  get: () => toDt(start.value).slice(0, 10),
  set: (v) => v && goto(startOfDay(parseDt(`${v} 00:00:00`))),
})
const days = computed(() => Array.from({ length: DAYS }, (_, i) => addDays(start.value, i)))
const end = computed(() => addDays(start.value, DAYS))
const location = ref('')
const rentalType = ref('')
const options = reactive({ locations: [], rental_types: [] })
const opt = (values, placeholder) => [{ label: placeholder, value: '' }, ...values.map((v) => ({ label: v, value: v }))]
const units = ref([])
const loading = ref(false)
const message = ref(null)
const quick = ref(null)
const dragging = ref(null)
const dragOver = ref('')
const selection = ref(null)

const isToday = (d) => startOfDay(new Date()).getTime() === d.getTime()
const goto = (d) => (start.value = d)
let flashTimer
function flash(text, ok = false) {
  message.value = { text, ok }
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => (message.value = null), 6000)
}

async function load() {
  loading.value = true
  try {
    const res = await api('availability.timeline', {
      from_datetime: toDt(start.value),
      to_datetime: toDt(end.value),
      location: location.value || undefined,
      rental_type: rentalType.value || undefined,
    })
    units.value = res.units
  } catch (e) {
    flash(e.messages?.[0] || __('Could not load the calendar'))
  } finally {
    loading.value = false
  }
}
watch([start, location, rentalType], load)
onMounted(async () => {
  load()
  try {
    Object.assign(options, await api('booking.list_options'))
  } catch {
    /* filters stay empty */
  }
})

function barStyle(e) {
  const s = Math.max((parseDt(e.start) - start.value) / DAY_MS, 0)
  const f = Math.min((parseDt(e.end) - start.value) / DAY_MS, DAYS)
  return { left: `calc(${(s / DAYS) * 100}% + 2px)`, width: `calc(${(Math.max(f - s, 0.15) / DAYS) * 100}% - 4px)` }
}

// Instant client-side check; the server checks again and has the final word.
function clashes(unit, from, to, ignore) {
  return unit.events.some((e) => e.name !== ignore && parseDt(e.start) < to && parseDt(e.end) > from)
}

// Drag across empty days to create
function beginSelect(u, i) {
  selection.value = { unit: u, from: i, to: i }
}
function extendSelect(u, i) {
  if (selection.value && selection.value.unit.name === u.name) selection.value.to = i
}
const inSelection = (u, i) => {
  const s = selection.value
  return s && s.unit.name === u.name && i >= Math.min(s.from, s.to) && i <= Math.max(s.from, s.to)
}
function endSelect() {
  const s = selection.value
  selection.value = null
  if (!s) return
  const from = addDays(start.value, Math.min(s.from, s.to))
  const to = addDays(start.value, Math.max(s.from, s.to) + 1)
  if (clashes(s.unit, from, to)) return flash(__('{0} is not free for those days', [s.unit.unit_name]))
  quick.value = {
    rentalItem: s.unit.rental_item,
    rentalType: s.unit.rental_type,
    rentalUnit: s.unit.name,
    itemName: s.unit.item_name,
    unitName: s.unit.unit_name,
    start: from,
    end: to,
  }
}

// Drag a bar to move it: keep its length and time of day, shift by whole days
async function drop(u, i) {
  dragOver.value = ''
  const d = dragging.value
  dragging.value = null
  if (!d) return
  const e = d.event
  const s = parseDt(e.start)
  const shift = Math.round((addDays(start.value, i) - startOfDay(s)) / DAY_MS)
  const from = addDays(s, shift)
  const to = addDays(parseDt(e.end), shift)
  if (shift === 0 && u.name === d.unit.name) return
  if (u.rental_item !== d.unit.rental_item) return flash(__('{0} can only move to another unit of the same item', [e.name]))
  if (clashes(u, from, to, e.name)) return flash(__('{0} is not free for those days', [u.unit_name]))
  try {
    await api('booking.move', {
      name: e.name,
      from_datetime: toDt(from),
      to_datetime: toDt(to),
      rental_unit: u.name === d.unit.name ? undefined : u.name,
    })
    flash(__('Moved {0}', [e.name]), true)
  } catch (err) {
    flash(err.messages?.[0] || __('Could not move the booking'))
  }
  load()
}
</script>
