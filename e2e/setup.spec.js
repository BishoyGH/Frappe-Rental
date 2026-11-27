import { expect, test } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'
const control = (page, id, tag) => page.locator(`${tag}[data-testid="${id}"], [data-testid="${id}"] ${tag}`).first()
async function choose(page, id, option) {
  await page.locator(`[data-testid="${id}"][role="combobox"], [data-testid="${id}"] [role="combobox"]`).first().click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

test.beforeEach(async ({ page }) => {
  // `bench serve` has no socket.io server; its error page leaks a DB transaction that blocks schema changes
  await page.route('**/socket.io/**', (route) => route.abort())
  await page.route('**/favicon.ico', (route) => route.abort())
  const res = await page.request.post('/api/method/login', { data: { usr: 'Administrator', pwd: ADMIN_PASSWORD } })
  expect(res.ok()).toBeTruthy()
})

test('define the Boat example end to end in the UI', async ({ page }) => {
  test.setTimeout(90000)
  const tag = Math.random().toString(36).slice(2, 7)
  const typeName = `Boat ${tag}`
  const field = `seats_${tag}`

  // Item type with a custom field on items
  await page.goto('/rental/item-types')
  await page.getByTestId('new-record').click()
  await expect(page).toHaveURL(/\/item-types\/new$/)
  await page.getByLabel('Name *').fill(typeName)
  await page.getByLabel('Buffer after (min)').fill('45')
  await page.getByTestId('cf-add').click()
  const cf = page.getByTestId('cf-row').first()
  await cf.locator('input[type="text"]').nth(0).fill('Seats')
  await cf.locator('input[type="text"]').nth(1).fill(field)
  await cf.getByRole('combobox').nth(1).click()
  await page.getByRole('option', { name: 'Int', exact: true }).click()
  await page.getByTestId('save-record').click()
  await expect(page).toHaveURL(new RegExp(`/rental/item-types/${encodeURIComponent(typeName)}$`))
  await expect(page.getByTestId('cf-row')).toHaveCount(1)

  // Item of that type: its custom field appears in the form
  await page.goto('/rental/items/new')
  await expect(page.getByTestId('setup-form')).toBeVisible()
  await page.getByLabel('Name *').fill(`Speedboat ${tag}`)
  await page.getByRole('combobox', { name: 'Item type *' }).click()
  await page.getByRole('option', { name: typeName, exact: true }).click()
  await page.getByRole('combobox', { name: 'Rate card' }).click()
  await page.getByRole('option', { name: 'E2E Card', exact: true }).click()
  await page.getByLabel('Seats').fill('8')
  await page.getByTestId('save-record').click()
  await expect(page).toHaveURL(/\/rental\/items\/RI-/)
  await expect(page.getByLabel('Seats')).toHaveValue('8')

  // Unit from the item page
  await page.getByTestId('add-unit').click()
  await expect(page).toHaveURL(/\/units\/new/)
  await expect(page.getByTestId('setup-form')).toBeVisible()
  await page.getByLabel('Name *').fill(`Boat 1 ${tag}`)
  await page.getByTestId('save-record').click()
  await expect(page).toHaveURL(/\/rental\/units\/RU-/)

  // Customer
  await page.goto('/rental/customers/new')
  await expect(page.getByTestId('setup-form')).toBeVisible()
  await page.getByLabel('Name *').fill(`Sailor ${tag}`)
  await page.getByTestId('save-record').click()
  await expect(page).toHaveURL(/\/rental\/customers\/.+/)
  await expect(page.getByTestId('setup-rail')).toContainText('No bookings yet')

  // The boat is now bookable
  await page.goto('/rental/availability')
  await choose(page, 'av-type', typeName)
  await page.getByTestId('av-search').click()
  await expect(page.getByTestId('av-row')).toContainText(`Boat 1 ${tag}`)
})
