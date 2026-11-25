# D6. Flexible invoicing (extends `DECISIONS.md`, overrides `PLAN.md` 4.5)

Goal: billing is independent of the rental period. A device rented for 12 months can be billed quarterly, a hotel stay once at check-out, a storage unit monthly in advance, a photographer shoot 50% up front and 50% on delivery.

## Billing plan
A **Rental Billing Plan** (child of Booking or Contract, defaulted from the Item type) defines how and when to invoice:

| Field | Options |
|---|---|
| `frequency` | One-off, Weekly, Monthly, Quarterly, Semi-annual, Yearly, Custom interval (every N days/months), Milestones |
| `timing` | In advance (start of period), In arrears (end of period), At check-in, At check-out, At confirmation |
| `first_invoice` | At confirmation, At start date, Custom date |
| `alignment` | Rental anniversary, Calendar period start (1st of month/quarter), Specific day of month |
| `proration` | None, Daily pro-rata for partial first/last period, Full first period |
| `amount_basis` | Rate x elapsed units (default), Fixed amount per period, Percent of total (milestones), Metered usage |
| `payment_terms` | ERPNext Payment Terms Template, auto-collect via saved gateway token (optional) |
| `invoice_grouping` | One invoice per booking, per contract, or one consolidated invoice per customer per period |
| `end_behaviour` | Stop at end date, Auto-renew, Continue until closed (open-ended) |

## Example: device rented 12 months, billed quarterly
- Booking 1 Jan to 31 Dec, rate 1,200/month, plan: Quarterly, in advance, aligned to calendar quarter.
- Schedule generated at confirmation (editable, previewed on the booking): 4 rows, each 3,600 on 1 Jan, 1 Apr, 1 Jul, 1 Oct. A booking starting 15 Jan with proration produces a short first period then calendar quarters.
- A daily job creates each Sales Invoice when due (draft or submitted per setting) and emails it. Payment follows ERPNext payment terms.
- Deposit is separate (liability account). Early return recalculates the remaining rows: the last invoice is prorated and unused prepaid amounts are credited (Credit Note) or kept per the cancellation policy.

## Data model
- **Rental Billing Plan** (child table, one per booking or contract): fields above.
- **Rental Billing Schedule** (child rows, generated): `period_from`, `period_to`, `invoice_date`, `amount`, `status` (Planned, Invoiced, Paid, Skipped, Credited), `sales_invoice`, `adjustment_note`. Rows are editable until invoiced.
- **Rental Billable Event** (optional queue): extra charges that join the next invoice (late fee, damage, delivery, metered usage, extension).
- Subscription is used only when the plan is a simple fixed recurring amount; otherwise the schedule drives invoice creation directly. Both write standard Sales Invoices, so reports and taxes are unchanged.

## Rules
1. **Plan precedence**: Booking plan overrides Contract plan, which overrides Item type default, which overrides Settings default.
2. **Change handling**: extending, shortening or repricing a booking regenerates only un-invoiced schedule rows and creates adjustment lines (or Credit Notes) for invoiced ones. Posted invoices are never edited.
3. **Metered usage**: a unit can record readings (hours, km, pages, kWh) at handover or via API; billed as quantity x rate with an included allowance and overage rate.
4. **Minimum commitment**: optional minimum term; early termination fee is a Billable Event.
5. **Price changes in term**: indexation rule (percent increase on anniversary) applies to future schedule rows.
6. **Customer-facing**: the portal shows the upcoming schedule, invoices and payment status; reminders go out before invoice date and after due date.
7. **Accounting**: advance-billed periods that straddle month end use Deferred Revenue (D5.4). Arrears billing accrues nothing; revenue is recognised when invoiced, unless the type enables accrual (Journal Entry job, optional).
8. **Idempotency**: the daily job locks per schedule row and stores the invoice link, so reruns never double-bill.

## UI
Booking page gets a **Billing** tab: pick a preset (One-off, Monthly, Quarterly, Yearly, Milestones, Custom), preview the schedule table, edit dates or amounts, and see invoice status per row. Item types hold the default plan.

## Roadmap impact
Billing plan, schedule and daily invoicing job move into Phase 2 (about 2 extra weeks); metered usage and consolidated invoices are Phase 5.
