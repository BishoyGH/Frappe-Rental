// Shared Playwright fixture: a signed-in Administrator page with the dev-server workarounds applied.
// Data is seeded through frappe_rental.api.* (see `api` below) or `bench execute frappe_rental.tests.e2e_fixtures.setup`.
import { test as base, expect } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

export const test = base.extend({
  page: async ({ page }, use) => {
    // `bench serve` has no socket.io server and no website assets; its error page leaks a DB transaction
    await page.route('**/socket.io/**', (route) => route.abort())
    await page.route('**/favicon.ico', (route) => route.abort())
    const res = await page.request.post('/api/method/login', { data: { usr: 'Administrator', pwd: ADMIN_PASSWORD } })
    expect(res.ok()).toBeTruthy()
    await use(page)
  },
  api: async ({ page }, use) => {
    await use(async (method, params = {}) => {
      const res = await page.request.post(`/api/method/frappe_rental.api.${method}`, {
        data: params,
        headers: { 'X-Frappe-CSRF-Token': 'test' },
      })
      expect(res.ok(), await res.text()).toBeTruthy()
      return (await res.json()).message
    })
  },
})
export { expect }
