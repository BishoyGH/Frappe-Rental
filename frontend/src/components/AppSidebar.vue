<template>
  <aside
    class="hidden w-56 shrink-0 flex-col gap-0.5 border-r bg-surface-menu-bar p-2 sm:flex"
    data-testid="sidebar"
  >
    <div class="mb-1.5 flex items-center gap-2 rounded p-1.5">
      <div class="grid h-7 w-7 place-items-center rounded-md bg-gray-900 text-sm font-semibold text-white">R</div>
      <div class="leading-tight">
        <div class="text-base font-semibold">Rental</div>
        <div class="text-xs text-ink-gray-5">{{ boot.company }}</div>
      </div>
    </div>
    <template v-for="section in sections" :key="section.title || 'main'">
      <div v-if="section.title" class="mx-2 mb-0.5 mt-2.5 text-xs font-medium text-ink-gray-5">
        {{ section.title }}
      </div>
      <router-link
        v-for="item in section.items"
        :key="item.route"
        :to="{ name: item.route }"
        class="flex items-center gap-2 rounded px-2 py-1.5 text-base text-ink-gray-7 hover:bg-surface-gray-2"
        active-class="bg-surface-white font-medium text-ink-gray-9 shadow-sm"
      >
        <component :is="icons[item.icon]" class="h-4 w-4 text-ink-gray-6" />
        {{ item.label }}
      </router-link>
    </template>
    <div class="mt-auto flex items-center gap-2 rounded p-1.5 text-sm text-ink-gray-7">
      <Avatar :label="boot.full_name || boot.user" size="sm" />
      <span class="truncate">{{ boot.full_name || boot.user }}</span>
      <a href="/app" class="ml-auto text-xs text-ink-gray-5 hover:underline">Desk</a>
    </div>
  </aside>
</template>

<script setup>
import { Avatar } from 'frappe-ui'
import LucideBadgeDollarSign from '~icons/lucide/badge-dollar-sign'
import LucideBox from '~icons/lucide/box'
import LucideCalendar from '~icons/lucide/calendar'
import LucideCalendarRange from '~icons/lucide/calendar-range'
import LucideFileText from '~icons/lucide/file-text'
import LucideLayoutDashboard from '~icons/lucide/layout-dashboard'
import LucidePackage from '~icons/lucide/package'
import LucideSearch from '~icons/lucide/search'
import LucideSettings from '~icons/lucide/settings'
import LucideSettings2 from '~icons/lucide/settings-2'
import LucideTag from '~icons/lucide/tag'
import LucideUsers from '~icons/lucide/users'
import { boot } from '../boot'
import { sections } from '../nav'

const icons = {
  'badge-dollar-sign': LucideBadgeDollarSign,
  box: LucideBox,
  calendar: LucideCalendar,
  'calendar-range': LucideCalendarRange,
  'file-text': LucideFileText,
  'layout-dashboard': LucideLayoutDashboard,
  package: LucidePackage,
  search: LucideSearch,
  settings: LucideSettings,
  'settings-2': LucideSettings2,
  tag: LucideTag,
  users: LucideUsers,
}
</script>
