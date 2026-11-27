import { expect, test } from './fixtures.js'

// Desk specs need the desk assets: `bench build --app frappe` (CI does this).
test('desk: Install Presets button on the Rental Type list', async ({ page }) => {
  await page.goto('/app/rental-type')
  await page.getByRole('button', { name: 'Install Presets' }).click()
  await expect(page.getByText(/Installed:/)).toBeVisible()
  // 13 presets plus the e2e types fill more than one list page, so look the preset up by name
  await page.goto('/app/rental-type?name=Device')
  await expect(page.locator('.list-row').filter({ hasText: 'Device' }).first()).toBeVisible()
})

test('desk: a Rental Type custom field shows on the Rental Item form', async ({ page, api }) => {
  const tag = Math.random().toString(36).slice(2, 7)
  await api('setup.save_record', {
    doctype: 'Rental Type',
    data: JSON.stringify({
      type_name: `Desk ${tag}`,
      custom_fields: [{ applies_to: 'Rental Item', label: `Hull ${tag}`, fieldname: `hull_${tag}`, fieldtype: 'Data' }],
    }),
  })
  await page.goto('/app/rental-item/new')
  await expect(page.locator(`[data-fieldname="hull_${tag}"]`).first()).toBeAttached()
  await expect(page.getByText(`Hull ${tag}`).first()).toBeVisible()
})
