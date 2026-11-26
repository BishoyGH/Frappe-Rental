import { createRouter, createWebHistory } from 'vue-router'
import { pages } from './nav'
import Placeholder from './pages/Placeholder.vue'

const slug = (label) => label.toLowerCase().replace(/\s+/g, '-')

const routes = [
  { path: '/', redirect: { name: 'Bookings' } },
  ...pages.map((p) => ({
    path: `/${slug(p.label)}`,
    name: p.route,
    component: Placeholder,
    meta: { title: p.label },
  })),
  { path: '/:pathMatch(.*)*', redirect: { name: 'Bookings' } },
]

const router = createRouter({ history: createWebHistory('/rental'), routes })
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Rental` : 'Rental'
})
export default router
