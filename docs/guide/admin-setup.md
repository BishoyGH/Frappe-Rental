# Admin setup

## 1. Install

```
bench get-app frappe_rental <repository url>
bench --site <site> install-app frappe_rental
bench --site <site> migrate
```

ERPNext must be installed first and its setup wizard finished. Install creates, for the first company (and for
any company added later):

- Accounts: Rental Income, Customer Deposits (Rental) as a liability, Late Fee Income, Damage Recovery,
  Deposit Forfeiture Income.
- Item Group **Rentals**, Warehouse **Rented Out**, the Accounting Dimension **Rental Item Type**.
- Roles: Rental Admin, Rental Manager, Rental Agent, Rental Accountant, Rental Provider, Rental Customer.

Try it with demo data on a test site: `bench --site <site> rental-demo` (every preset; `--basic` for Device
and Apartment only, `--with-bookings` for a sample booking). It is safe to run twice.

## 2. Rental Settings

Open **Rental Settings** and check:

| Setting | What it does |
| --- | --- |
| Default Company, Default Price List | used when a booking does not say otherwise |
| Hold Expiry (minutes) | how long a held booking keeps its units before returning to Draft |
| Auto Invoice | bill due rows as soon as a booking is confirmed, instead of waiting for the daily job |
| Submit scheduled invoices | submit invoices made by the daily job (off leaves them as drafts to review) |
| Grace Period, Late Fee Rate | late returns: minutes allowed, then a fee as a percent of the daily rate |
| Accounts | the five accounts above; change them if your chart uses other names |

## 3. Rental Types

Install presets from the Rental Type list (**Install Presets**) and adjust each type you use:

- **Time unit** and minimum/maximum duration.
- **Identification**: None, Serial, Batch, Asset or Pooled. This decides what a unit needs (a Serial No, a
  Batch, an Asset, or a quantity).
- **Buffers** before and after each booking, used for cleaning or transport.
- **Requires hold / deposit / contract / check-in / return inspection**.
- **Billing plan** (one-off, weekly, monthly, quarterly, milestones, and so on), deposit rule, cancellation
  policy, tax template and income account.
- **Metered usage**: meter unit, included allowance per booking and overage rate.
- **Turnaround task on return**: creates a cleaning task and keeps the unit in Turnaround until done.

## 4. Locations, rate cards, items and units

1. **Rental Location**: one per branch, with its timezone. A cost center is created for each.
2. **Rental Rate Card**: rates per time unit, seasons, customer-group prices, duration tiers and charges.
3. **Rental Item**: type, rate card, location, photos and amenities; tick *Published* to show it on the website.
4. **Rental Unit**: one per serial, asset, batch or pool. Provider units link an Employee and **Working Hours**
   (a Rental Schedule with weekly slots and a holiday list).

Bulk import items, units and customers from CSV with the setup import (dry run first).

## 5. Contracts

Build a clause library (**Rental Clause**) and a **Rental Terms Template**. A contract renders the template,
is sent for signature (with an optional emailed code), and becomes Active when signed and countersigned.
Allocations reserve units for the contract; visits are planned from the visit frequency.

## 6. Scheduled jobs

Make sure the scheduler is enabled (`bench --site <site> enable-scheduler`). The app runs:

- every 5 minutes: expire holds, remind about expiring holds;
- hourly: overdue returns, visit SLA checks, overdue turnaround tasks;
- daily: due invoices, waitlist expiry, signature reminders, contract notices and renewals.
