// Staff notification settings (T38) and the contracts list (T47): the screens open and the rules save.
import { expect, test } from '@playwright/test'

const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'

test.beforeEach(async ({ page }) => {
  await page.route('**/socket.io/**', (route) => route.abort())
  await page.route('**/favicon.ico', (route) => route.abort())
  const res = await page.request.post('/api/method/login', { data: { usr: 'Administrator', pwd: ADMIN_PASSWORD } })
  expect(res.ok()).toBeTruthy()
})

test('alert rules show the defaults and save a new rule', async ({ page }) => {
  await page.goto('/rental/settings')
  await expect(page.getByTestId('st-rules')).toBeVisible()
  expect(await page.getByTestId('st-rule').count()).toBeGreaterThan(0)
  await page.getByTestId('st-add').click()
  await page.getByTestId('st-save').click()
  await expect(page.getByTestId('st-message')).toBeVisible()
  await expect(page.getByTestId('st-no-alerts').or(page.getByTestId('st-alerts'))).toBeVisible()
})

test('contracts list opens', async ({ page }) => {
  await page.goto('/rental/contracts')
  await expect(page.getByTestId('page-title')).toHaveText('Contracts')
})
