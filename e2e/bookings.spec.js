import { expect, test } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

// Needs the data from frappe_rental.tests.e2e_fixtures.setup
test.beforeEach(async ({ page }) => {
  const res = await page.request.post('/api/method/login', { data: { usr: 'Administrator', pwd: ADMIN_PASSWORD } })
  expect(res.ok()).toBeTruthy()
})

// FormControl may put the test id on the control itself or on its wrapper
const control = (page, id, tag) => page.locator(`${tag}[data-testid="${id}"], [data-testid="${id}"] ${tag}`).first()

async function choose(page, id, option) {
  await page.locator(`[data-testid="${id}"][role="combobox"], [data-testid="${id}"] [role="combobox"]`).first().click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

async function pick(page, testid, text) {
  const input = control(page, testid, 'input')
  await input.fill(text)
  await page.getByRole('option', { name: new RegExp(text) }).first().click()
}

test('create, hold and confirm a booking, then find it in the list', async ({ page }) => {
  // A unique day per run so units stay free across reruns
  const day = 1 + Math.floor(Math.random() * 25)
  const month = 1 + Math.floor(Math.random() * 12)
  const year = 2030 + Math.floor(Math.random() * 50)
  const pad = (n) => String(n).padStart(2, '0')
  const from = `${year}-${pad(month)}-${pad(day)}T10:00`
  const to = `${year}-${pad(month)}-${pad(day + 2)}T10:00`

  await page.goto('/rental/bookings')
  await expect(page.getByTestId('bookings-table')).toBeVisible()
  await page.getByTestId('create').click()
  await expect(page).toHaveURL(/\/rental\/bookings\/new$/)

  await pick(page, 'customer', 'E2E Customer')
  await choose(page, 'rental-type', 'E2E Type')
  await control(page, 'from', 'input').fill(from)
  await control(page, 'to', 'input').fill(to)
  await pick(page, 'line-item', 'E2E Camera')
  await expect(page.getByTestId('quote-total')).toContainText('200')

  await page.getByTestId('save-hold').click()
  await expect(page).toHaveURL(/\/rental\/bookings\/RB-/)
  const name = decodeURIComponent(page.url().split('/').pop())
  await expect(page.getByTestId('status')).toHaveText('Hold')
  await expect(page.getByTestId('grand-total')).toContainText('200')
  await expect(page.getByTestId('lines')).toContainText('E2E Camera')

  await page.getByTestId('action-confirm').click()
  await expect(page.getByTestId('status')).toHaveText('Confirmed')
  await expect(page.getByTestId('activity').first()).toBeVisible()

  await page.getByRole('link', { name: 'Bookings' }).first().click()
  await page.getByTestId('filters').getByPlaceholder('Search ID or customer').fill(name)
  await expect(page.getByTestId('booking-row')).toHaveCount(1)
  await expect(page.getByTestId('booking-row')).toContainText('Confirmed')

  await choose(page, 'group-by', 'Group: status')
  await expect(page.getByTestId('group-row')).toContainText('Confirmed')

  await page.getByTestId('booking-row').click()
  await expect(page.getByTestId('page-title')).toHaveText(name)
})
