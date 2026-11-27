# Guide by role

## Rental Manager

- Sets up items, units, rate cards and contracts; reviews the dashboard (utilisation, revenue, overdue
  returns, SLA breaches).
- Moves bookings on the calendar (drafts and holds only), swaps or releases contract allocations with a reason,
  and amends signed contracts (each amendment keeps the previous terms).
- Reports: Utilisation, Revenue by type, Overdue returns, Deposits held, Damage, Upcoming bookings.

## Front desk (Rental Agent)

- **New booking**: pick dates, search availability (with prices), choose units, add the customer, hold, then
  confirm. Conflicts are refused on screen and on the server.
- **Check-out**: open the booking's Handover, scan each unit (barcode, serial, asset or unit code), fill the
  checklist and meter readings, get the signature, submit.
- **Return**: scan the units back, note condition (Good, Damaged, Missing) and meter readings. Late returns
  queue a late fee; damage opens a Damage Report; metered overage is billed; a turnaround task appears if the
  type uses one.
- **Deposits**: collect, apply to charges or refund from the booking's Deposit panel.
- **Cancellations** follow the type's cancellation policy; the preview shows the fee and refund first.

## Rental Accountant

- Reviews invoices made by the daily job (or drafts, when *Submit scheduled invoices* is off) and credit notes
  from shortenings, early returns and cancellations. Posted invoices are never edited.
- Customers with **Consolidate Rental Invoices** get one invoice per month for all their rentals, each line
  naming its booking.
- See [Accounting](accounting.md) for accounts and entries.

## Provider (photographer, technician, guide)

- Has an Employee linked to their user and a Provider unit with working hours. Bookings can only be made
  inside those hours and outside holidays.
- Sees their own schedule (`api.provider.my_schedule`, the provider screen), logs time on the booking's
  Project with a Timesheet (billable hours become a charge on the next invoice), and completes maintenance
  visits and turnaround tasks.

## Customer (portal)

- Books and pays online, sees bookings and invoices, signs contracts (typed or drawn signature, with a code by
  email when required), requests a service visit under a maintenance contract.

## Rental Admin

- Everything above, plus Rental Settings, roles and permissions, presets and imports.
