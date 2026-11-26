// Sidebar sections, in the order of the mockups. Pages not built yet show a placeholder.
export const sections = [
  {
    items: [
      { label: 'Dashboard', route: 'Dashboard', icon: 'layout-dashboard' },
      { label: 'Bookings', route: 'Bookings', icon: 'calendar' },
      { label: 'Calendar', route: 'Calendar', icon: 'calendar-range' },
      { label: 'Availability', route: 'Availability', icon: 'search' },
      { label: 'Contracts', route: 'Contracts', icon: 'file-text' },
      { label: 'Handovers', route: 'Handovers', icon: 'package' },
    ],
  },
  {
    title: 'Catalog',
    items: [
      { label: 'Items', route: 'Items', icon: 'tag' },
      { label: 'Units', route: 'Units', icon: 'box' },
      { label: 'Customers', route: 'Customers', icon: 'users' },
    ],
  },
  {
    title: 'Setup',
    items: [
      { label: 'Item types', route: 'ItemTypes', icon: 'settings-2' },
      { label: 'Rate cards', route: 'RateCards', icon: 'badge-dollar-sign' },
      { label: 'Settings', route: 'Settings', icon: 'settings' },
    ],
  },
]
export const pages = sections.flatMap((s) => s.items)
