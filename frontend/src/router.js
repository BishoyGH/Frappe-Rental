import { createRouter, createWebHistory } from 'vue-router'
import { pages } from './nav'
import Placeholder from './pages/Placeholder.vue'

const slug = (label) => label.toLowerCase().replace(/\s+/g, '-')
const built = {
  Bookings: () => import('./pages/BookingsList.vue'),
}

const routes = [
  { path: '/', redirect: { name: 'Bookings' } },
  ...pages.map((p) => ({
    path: `/${slug(p.label)}`,
    name: p.route,
    component: built[p.route] || Placeholder,
    meta: { title: p.label },
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
  { path: '/:pathMatch(.*)*', redirect: { name: 'Bookings' } },
]

const router = createRouter({ history: createWebHistory('/rental'), routes })
router.afterEach((to) => {
  const title = to.params.name || to.meta.title
  document.title = title ? `${title} · Rental` : 'Rental'
})
export default router
