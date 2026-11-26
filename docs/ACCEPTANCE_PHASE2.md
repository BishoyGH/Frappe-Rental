# Phase 2 acceptance (T32)

The scenarios run as `frappe_rental.tests.test_phase2_acceptance` on Frappe/ERPNext v15 and v16. Each one checks
that every posted voucher balances, and checks the figures below.

## Scenarios

| # | Scenario | What is checked |
|---|----------|-----------------|
| 1 | Quarterly device: 12 months at 300 a month, Quarterly plan, in advance | 4 schedule rows; 4 Sales Invoices (1 Jan, 1 Apr, 1 Jul, 1 Oct) adding up to the booking's net total; rerunning the daily job makes no new invoice |
| 2 | Hotel stay: 3 nights at 80 | Net 240; the Sales Invoice balances; check-out then return sets the booking to Returned and frees the room |
| 3 | Damage with deposit refund: Fixed deposit 500, damage approved at 150 | Collect 500, apply 150 to Damage Recovery, refund 350; the deposit ends with 0 held, and the deposit liability account nets to zero over the three Journal Entries |

## Expected GL (accountant review)

Scenario 3. Accounts come from Rental Settings.

| Step | Voucher | Debit | Credit |
|------|---------|-------|--------|
| Collect deposit | Journal Entry | Cash 500 | Customer Deposits (Rental) 500 |
| Damage from deposit | Journal Entry | Customer Deposits (Rental) 150 | Damage Recovery 150 |
| Refund the rest | Journal Entry | Customer Deposits (Rental) 350 | Cash 350 |

Scenario 1 (each quarter): Debtors 900 / Rental income 900, plus tax lines when a tax template is set.

## Checklist for the accountant

- [ ] Deposits never touch income: collection and refund go only through the liability account.
- [ ] Damage recovery goes to the Damage Recovery income account, and only after it is approved.
- [ ] Every period invoice links back to its booking (`rental_booking`) and to its schedule row (`rental_billing_row`).
- [ ] Cancelling or crediting creates Credit Notes; posted invoices are never edited.
- [ ] Deferred revenue, when the Rental Type enables it, sets service start and end dates on period invoices.
- [ ] Late fees and damage billed by invoice show as separate lines (Rental Billable Event).

GL screenshots are replaced by the tables above and by the assertions in the test module, because the CI
benches have no browser session to capture desk reports. To review on a site, run `bench rental-demo
--with-bookings` and open General Ledger filtered by voucher.
