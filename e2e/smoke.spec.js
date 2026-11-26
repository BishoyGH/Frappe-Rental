import { expect, test } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

test('guest is sent to login', async ({ page }) => {
  await page.goto('/rental/bookings')
  await expect(page).toHaveURL(/\/login\?redirect-to=/)
})

test('signed-in staff see the shell', async ({ page }) => {
  const res = await page.request.post('/api/method/login', {
    data: { usr: 'Administrator', pwd: ADMIN_PASSWORD },
  })
  expect(res.ok()).toBeTruthy()
  await page.goto('/rental')
  await expect(page).toHaveURL(/\/rental\/bookings$/)
  const sidebar = page.getByTestId('sidebar')
  await expect(sidebar).toBeVisible()
  for (const label of ['Dashboard', 'Bookings', 'Calendar', 'Availability', 'Items', 'Settings']) {
    await expect(sidebar.getByRole('link', { name: label })).toBeVisible()
  }
  await sidebar.getByRole('link', { name: 'Calendar' }).click()
  await expect(page.getByTestId('page-title')).toHaveText('Calendar')
  await expect(page).toHaveURL(/\/rental\/calendar$/)
})
