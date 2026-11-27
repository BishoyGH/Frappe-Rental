# Accounting guide

Everything posts through standard ERPNext documents. There is no separate rental ledger.

## Accounts

| Account | Type | Used for |
| --- | --- | --- |
| Rental Income | Income | rental lines (per type or per Item when overridden) |
| Customer Deposits (Rental) | Liability | deposits held |
| Late Fee Income | Income | late return fees |
| Damage Recovery | Income | damage charges |
| Deposit Forfeiture Income | Income | deposits kept |

Names and accounts are set in Rental Settings. A Rental Type's income account overrides the default.

## Bookings and invoices

- Confirming a booking creates a **Sales Order**. Invoices follow the booking's **billing plan**: one invoice
  for a short rental, or a schedule of rows (monthly, quarterly, milestones) that the daily job turns into
  **Sales Invoices**. Each row is billed once, even when the job runs twice.
- Changes after invoicing never edit posted invoices: extensions add rows, shortenings and early returns
  rebuild the rows not yet billed and issue a **Credit Note** for anything over-billed.
- Charges (late fees, damage, delivery, extensions, metered overage, timesheet hours, contract overage,
  termination fees) wait as **Rental Billable Events** and join the booking's next invoice, or get their own.
- Advance-billed periods can use **Deferred Revenue** when the Rental Type enables it, so income is
  recognised over the service dates.
- Customers can opt into **consolidated invoices**: one per month, company, currency and tax template.

## Deposits

Deposits move by **Journal Entry** on both ERPNext versions:

- Collect: Dr Bank or Cash, Cr Customer Deposits (Rental), with the customer as party.
- Apply to charges: Dr Customer Deposits, Cr the customer's receivable against the invoice, so the invoice's
  outstanding amount drops.
- Refund: Dr Customer Deposits, Cr Bank. Forfeit: Dr Customer Deposits, Cr Deposit Forfeiture Income.

VAT on applied or forfeited deposits is not posted automatically yet; post it by hand where your rules need it.

## Cancellations

The cancellation policy picks a tier by notice. The fee is invoiced; if an invoice exists, a Credit Note covers
the refunded part and the refund is a Payment Entry.

## Tax, cost centers and dimensions

- One Sales Taxes and Charges template per Rental Type (or per booking).
- Each Rental Location gets a **Cost Center**; invoices carry the **Rental Item Type** Accounting Dimension, so
  P&L by branch and by type comes from standard reports.
- Repairs from damage reports are ERPNext **Asset Repairs** on the asset.
