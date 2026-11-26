// My bookings portal (T37): a customer sees their own bookings, changes a held one and cancels with a preview.
import { expect, test } from '@playwright/test'

const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10)
const LOGIN = { usr: 'e2e-returning@example.com', pwd: 'E2e-Returning-1' }
let bike
let offset = 400 + Math.floor(Math.random() * 300)

test.beforeAll(async ({ request }) => {
  const res = await request.get('/api/method/frappe_rental.api.public.items', { params: { rental_type: 'E2E Shop Type' } })
  bike = (await res.json()).message.items.find((i) => i.item_name === 'E2E Bike').name
})

test.beforeEach(async ({ page }) => {
  await page.route('**/socket.io/**', (route) => route.abort())
  const res = await page.request.post('/api/method/login', { data: LOGIN })
  expect(res.ok()).toBeTruthy()
})

async function startHeld(page) {
  offset += 3
  const res = await page.request.post('/api/method/frappe_rental.api.checkout.start', {
    data: { booking: JSON.stringify({ item: bike, from_datetime: `${day(offset)} 10:00:00`, to_datetime: `${day(offset + 1)} 10:00:00`, details: {} }) },
    headers: { 'X-Frappe-CSRF-Token': 'test' },
  })
  expect(res.ok(), await res.text()).toBeTruthy()
  return (await res.json()).message.name
}

test('guest is asked to sign in', async ({ browser }) => {
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto('/rental/my-bookings')
  await expect(page.getByTestId('mb-login')).toBeVisible()
  await ctx.close()
})

test('list, change dates and cancel a held booking', async ({ page }) => {
  const name = await startHeld(page)
  await page.goto('/rental/my-bookings')
  await expect(page.getByTestId('mb-row').filter({ hasText: name })).toBeVisible()
  await page.getByTestId('mb-row').filter({ hasText: name }).click()
  await expect(page.getByTestId('mb-name')).toHaveText(name)
  await expect(page.getByTestId('mb-total')).toContainText('40.00')

  await page.locator('[data-testid="mb-to"] input, input[data-testid="mb-to"]').fill(`${day(offset + 2)}T10:00`)
  await page.getByTestId('mb-save').click()
  await expect(page.getByTestId('mb-message')).toContainText('Dates changed')
  await expect(page.getByTestId('mb-total')).toContainText('80.00')

  await page.getByTestId('mb-cancel').click()
  await expect(page.getByTestId('mb-preview')).toContainText('Nothing is charged')
  await page.getByTestId('mb-confirm-cancel').click()
  await expect(page.getByTestId('mb-message')).toContainText('Booking cancelled')
})

test('another customer cannot open the booking', async ({ page, browser }) => {
  const name = await startHeld(page)
  const ctx = await browser.newContext()
  const other = await ctx.newPage()
  await other.route('**/socket.io/**', (route) => route.abort())
  const email = `e2e-other-${Date.now()}@example.com`
  const res = await other.request.post('/api/method/frappe_rental.api.checkout.start', {
    data: { booking: JSON.stringify({ item: bike, from_datetime: `${day(offset + 40)} 10:00:00`, to_datetime: `${day(offset + 41)} 10:00:00`, details: { full_name: 'Other Person', email } }) },
    headers: { 'X-Frappe-CSRF-Token': 'test' },
  })
  expect(res.ok(), await res.text()).toBeTruthy()
  await other.goto(`/rental/my-bookings/${name}`)
  await expect(other.getByTestId('mb-error')).toContainText('not found')
  await ctx.close()
})
