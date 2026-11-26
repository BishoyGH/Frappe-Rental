import { expect, test } from './fixtures'

// T29: scan-first check-out and return, then settle the damage from the booking page.
// Needs the data from frappe_rental.tests.e2e_fixtures.setup
test('hand out, take back damaged, write off the damage', async ({ page, api }) => {
  const [item] = await api('booking.search_link', { doctype: 'Rental Item', txt: 'E2E Kit' })
  const [customer] = await api('booking.search_link', { doctype: 'Customer', txt: 'E2E Customer' })
  const year = 2100 + Math.floor(Math.random() * 800)
  const held = await api('booking.create', {
    booking: JSON.stringify({
      customer: customer.value,
      rental_type: 'E2E Kit Type',
      from_datetime: `${year}-03-03 10:00`,
      to_datetime: `${year}-03-05 10:00`,
      lines: [{ rental_item: item.value }],
    }),
    hold: 1,
  })
  await api('booking.confirm', { name: held.name })

  await page.goto('/rental/handovers')
  await page.getByTestId('ho-scan').locator('input').or(page.locator('input[data-testid="ho-scan"]')).first().fill(held.name)
  await page.getByTestId('ho-find').click()
  await expect(page.getByTestId('ho-booking')).toHaveText(held.name)
  await expect(page.getByTestId('ho-step')).toHaveText('Check-out')
  await page.getByRole('button', { name: 'Pick all' }).click()
  await page.getByTestId('ho-submit').click()
  await expect(page.getByTestId('ho-message')).toBeVisible()
  await expect(page.getByTestId('ho-step')).toHaveText('Return')

  await page.getByRole('button', { name: 'Pick all' }).click()
  await page.locator('[data-testid^="ho-cond-"]').first().selectOption('Damaged')
  await page.getByTestId('ho-submit').click()
  await expect(page.getByTestId('ho-done')).toBeVisible()
  await expect(page.getByTestId('ho-history')).toHaveCount(2)

  await page.goto(`/rental/bookings/${held.name}`)
  await page.getByTestId('tabs').getByRole('button', { name: 'Deposit & damage' }).click()
  await expect(page.getByTestId('dmg-report')).toHaveCount(1)
  await page.getByTestId('dmg-writeoff').click()
  await expect(page.getByTestId('dmg-status')).toHaveText('Written Off')
})

test('billing tab lists the schedule', async ({ page, api }) => {
  const [item] = await api('booking.search_link', { doctype: 'Rental Item', txt: 'E2E Kit' })
  const [customer] = await api('booking.search_link', { doctype: 'Customer', txt: 'E2E Customer' })
  const year = 2100 + Math.floor(Math.random() * 800)
  const held = await api('booking.create', {
    booking: JSON.stringify({
      customer: customer.value,
      rental_type: 'E2E Kit Type',
      from_datetime: `${year}-06-03 10:00`,
      to_datetime: `${year}-06-06 10:00`,
      lines: [{ rental_item: item.value }],
    }),
    hold: 1,
  })
  await page.goto(`/rental/bookings/${held.name}`)
  await page.getByTestId('tabs').getByRole('button', { name: 'Billing' }).click()
  await expect(page.getByTestId('bill-row').first()).toBeVisible()
  await expect(page.getByTestId('bill-total')).toContainText('300')
})
