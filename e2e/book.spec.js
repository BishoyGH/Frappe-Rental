// Customer booking flow (T35): a guest books and gets an account; a returning customer signs in and books.
import { expect, test } from '@playwright/test'

const day = (n) => {
  const d = new Date(Date.now() + n * 86400000)
  return d.toISOString().slice(0, 10)
}
// FormControl puts the test id on the input itself
const field = (page, id) => page.locator(`[data-testid="${id}"] input, input[data-testid="${id}"]`)
let offset = 30 + Math.floor(Math.random() * 300)

async function pickDates(page) {
  offset += 2
  await page.goto(`/rental/book?item=${encodeURIComponent(bike)}`)
  await field(page, 'book-from').fill(`${day(offset)}T10:00`)
  await field(page, 'book-to').fill(`${day(offset + 1)}T10:00`)
  await page.getByTestId('book-next').click()
  await page.getByTestId('book-extra-E2E Helmet').locator('input').check()
  await page.getByTestId('book-next').click()
}

let bike
test.beforeAll(async ({ request }) => {
  const res = await request.get('/api/method/frappe_rental.api.public.items', { params: { rental_type: 'E2E Shop Type' } })
  bike = (await res.json()).message.items.find((i) => i.item_name === 'E2E Bike').name
})

test.beforeEach(async ({ page }) => {
  await page.route('**/socket.io/**', (route) => route.abort())
})

test('guest books and an account is created', async ({ page }) => {
  await pickDates(page)
  await field(page, 'book-name').fill('Gale Guest')
  await field(page, 'book-email').fill(`e2e-guest-${Date.now()}@example.com`)
  await page.getByTestId('book-start').click()
  await expect(page.getByTestId('book-total')).toContainText('45.00')
  await page.getByTestId('book-confirm').click()
  await expect(page.getByTestId('book-done')).toContainText('is confirmed')
  const me = await page.request.get('/api/method/frappe.auth.get_logged_user')
  expect((await me.json()).message).toContain('e2e-guest-')
})

test('returning customer signs in and books', async ({ page }) => {
  const res = await page.request.post('/api/method/login', { data: { usr: 'e2e-returning@example.com', pwd: 'E2e-Returning-1' } })
  expect(res.ok()).toBeTruthy()
  await pickDates(page)
  await expect(page.getByTestId('book-as')).toContainText('Robin Returning')
  await page.getByTestId('book-start').click()
  await page.getByTestId('book-confirm').click()
  await expect(page.getByTestId('book-done')).toContainText('is confirmed')
})

test('guest cannot reuse an existing email', async ({ page }) => {
  await pickDates(page)
  await field(page, 'book-name').fill('Someone')
  await field(page, 'book-email').fill('e2e-returning@example.com')
  await page.getByTestId('book-start').click()
  await expect(page.getByTestId('book-error')).toContainText('Sign in')
})
