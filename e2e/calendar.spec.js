import { expect, test } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'
const pad = (n) => String(n).padStart(2, '0')
// A random far-future fortnight per run so earlier runs' bookings never collide
const randomDay = () => {
  const d = new Date(2030 + Math.floor(Math.random() * 60), Math.floor(Math.random() * 12), 1 + Math.floor(Math.random() * 10))
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const control = (page, id, tag) => page.locator(`${tag}[data-testid="${id}"], [data-testid="${id}"] ${tag}`).first()
async function choose(page, id, option) {
  await page.locator(`[data-testid="${id}"][role="combobox"], [data-testid="${id}"] [role="combobox"]`).first().click()
  await page.getByRole('option', { name: option, exact: true }).click()
}
async function holdInDialog(page) {
  const dialog = page.getByTestId('quick-book')
  await control(page, 'qb-customer', 'input').fill('E2E Customer')
  await page.getByRole('option', { name: /E2E Customer/ }).first().click()
  await expect(dialog.getByTestId('qb-price')).toBeVisible()
  await dialog.getByTestId('qb-save').click()
}

test.beforeEach(async ({ page }) => {
  // `bench serve` has no socket.io server; its error page leaks a DB transaction that blocks schema changes
  await page.route('**/socket.io/**', (route) => route.abort())
  await page.route('**/favicon.ico', (route) => route.abort())
  const res = await page.request.post('/api/method/login', { data: { usr: 'Administrator', pwd: ADMIN_PASSWORD } })
  expect(res.ok()).toBeTruthy()
})

test('availability search and quick book', async ({ page }) => {
  const day = randomDay()
  const next = day.slice(0, 8) + pad(Number(day.slice(8)) + 1)
  await page.goto('/rental/availability')
  await choose(page, 'av-type', 'E2E Type')
  await control(page, 'av-from', 'input').fill(`${day}T09:00`)
  await control(page, 'av-to', 'input').fill(`${next}T09:00`)
  await page.getByTestId('av-search').click()
  await expect(page.getByTestId('av-row').first()).toContainText('E2E Camera')
  await page.getByTestId('av-book').first().click()
  await holdInDialog(page)
  await expect(page).toHaveURL(/\/rental\/bookings\/RB-/)
  await expect(page.getByTestId('status')).toHaveText('Hold')
})

test('calendar: drag to create, move, and reject a clash', async ({ page }) => {
  test.setTimeout(90000)
  await page.goto('/rental/calendar')
  await choose(page, 'cal-type', 'E2E Type')
  await control(page, 'cal-start', 'input').fill(randomDay())
  const rows = page.getByTestId('cal-row')
  await expect(rows).toHaveCount(3)
  const [u1, u2] = [await rows.nth(0).getAttribute('data-unit'), await rows.nth(1).getAttribute('data-unit')]
  const cell = (unit, day) => page.locator(`[data-testid="cal-cell"][data-unit="${unit}"][data-day="${day}"]`)
  const dragCreate = async (unit, from, to) => {
    await cell(unit, from).hover()
    await page.mouse.down()
    await cell(unit, to).hover()
    await page.mouse.up()
    await holdInDialog(page)
    await expect(page.getByTestId('cal-message')).toContainText('held')
  }

  // Create on unit 1, days 1-2
  await dragCreate(u1, 1, 2)
  const first = page.locator('[data-testid="cal-event"]').first()
  await expect(first).toBeVisible()

  // Move it to days 5-6 on the same unit
  await first.dragTo(cell(u1, 5))
  await expect(page.getByTestId('cal-message')).toContainText('Moved')

  // Book unit 2 on days 5-6, then try to drop unit 1's booking on top: rejected
  await dragCreate(u2, 5, 6)
  const name = await first.getAttribute('data-name')
  await page.locator(`[data-testid="cal-event"][data-name="${name}"]`).dragTo(cell(u2, 5), { force: true }) // the cell sits under unit 2's bar
  await expect(page.getByTestId('cal-message')).toContainText('not free')
  expect(await page.locator('[data-testid="cal-event"]').count()).toBe(2)
})
