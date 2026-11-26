import { createRouter, createWebHistory } from 'vue-router'
import { pages } from './nav'
import Placeholder from './pages/Placeholder.vue'

const slug = (label) => label.toLowerCase().replace(/\s+/g, '-')
const built = {
  Bookings: () => import('./pages/BookingsList.vue'),
  Calendar: () => import('./pages/CalendarPage.vue'),
  Availability: () => import('./pages/AvailabilityPage.vue'),
  Handovers: () => import('./pages/HandoversPage.vue'),
  Contracts: () => import('./pages/ContractsList.vue'),
}
const SETUP = ['ItemTypes', 'Items', 'Units', 'Customers']

const routes = [
  { path: '/', redirect: { name: 'Bookings' } },
  ...pages.map((p) => ({
    path: `/${slug(p.label)}`,
    name: p.route,
    component: SETUP.includes(p.route) ? () => import('./pages/SetupList.vue') : built[p.route] || Placeholder,
    props: SETUP.includes(p.route) ? { screenKey: p.route } : false,
    meta: { title: p.label },
  })),
  ...pages
    .filter((p) => SETUP.includes(p.route))
    .map((p) => ({
      path: `/${slug(p.label)}/:name`,
      name: `${p.route}Form`,
      component: () => import('./pages/SetupForm.vue'),
      props: (r) => ({ screenKey: p.route, name: r.params.name }),
      meta: { title: p.label, section: p.route },
    })),
  {
    path: '/bookings/new',
    name: 'BookingNew',
    component: () => import('./pages/BookingNew.vue'),
    meta: { title: 'New booking', section: 'Bookings' },
  },
  {
    path: '/bookings/:name',
    name: 'BookingDetail',
    component: () => import('./pages/BookingDetail.vue'),
    props: true,
    meta: { title: 'Booking', section: 'Bookings' },
  },
  {
    path: '/book',
    name: 'Book',
    component: () => import('./pages/BookFlow.vue'),
    meta: { title: 'Book', public: true },
  },
  {
    path: '/contracts/:name',
    name: 'ContractDetail',
    component: () => import('./pages/ContractDetail.vue'),
    props: true,
    meta: { title: 'Contract', section: 'Contracts' },
  },
  {
    path: '/my-contracts',
    name: 'MyContracts',
    component: () => import('./pages/MyContracts.vue'),
    meta: { title: 'My contracts', public: true },
  },
  {
    path: '/my-contracts/:name',
    name: 'MyContractDetail',
    component: () => import('./pages/MyContractDetail.vue'),
    props: true,
    meta: { title: 'My contract', public: true },
  },
  {
    path: '/my-bookings',
    name: 'MyBookings',
    component: () => import('./pages/MyBookings.vue'),
    meta: { title: 'My bookings', public: true },
  },
  {
    path: '/my-bookings/:name',
    name: 'MyBookingDetail',
    component: () => import('./pages/MyBookingDetail.vue'),
    props: true,
    meta: { title: 'My booking', public: true },
  },
  { path: '/:pathMatch(.*)*', redirect: { name: 'Bookings' } },
]

const router = createRouter({ history: createWebHistory('/rental'), routes })
router.afterEach((to) => {
  const title = to.params.name || to.meta.title
  document.title = title ? `${title} · Rental` : 'Rental'
})
export default router
