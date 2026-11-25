# Frappe Rental: Product and Technical Plan

App name: `frappe_rental` (Frappe v15, requires `erpnext`). Module: **Rental**.
One generic engine that rents **resources** (apartments, hotel rooms, devices, storage units) and **services** (photographers, maintenance contracts) with shared booking, pricing, billing and contract flows.

Screen mockups: https://claude.ai/artifact/GWrCpQ4YQmxYKq34oEZmjY

## 1. Goals and scope

**Goals**
1. One booking engine for anything time-based: hourly, daily, nightly, monthly, or per-visit.
2. Reuse ERPNext for money and stock: Item, Customer, Sales Order, Sales Invoice, Payment Entry, Asset, Subscription, Project, Timesheet. No parallel accounting.
3. Prevent double booking, with a calendar and availability search for staff and customers.
4. Self-service customer portal: search, book, pay a deposit, sign, manage bookings.
5. Configurable per business type with no code, using *Rental Type* templates.

**In scope (v1 to v3)**: availability, quotes and bookings, pricing rules, deposits, recurring billing, contracts with e-signature, check-in/out and returns with condition reports, damage charges, cancellation policies, portal, REST API, dashboards, reports.

**Out of scope for now**: channel managers (Booking.com/Airbnb sync), dynamic AI pricing, native mobile apps (portal is a responsive PWA), multi-currency pricing per item.

**Personas**: Admin, Rental Manager, Front Desk, Technician/Provider (photographer, maintenance engineer), Accountant, Customer (portal user).

## 2. The generic rentable model

Two kinds of thing are booked, so the model has one abstraction with two modes.

| Concept | Resource mode | Service mode |
|---|---|---|
| Examples | Apartment, hotel room, camera, storage unit | Photographer, cleaner, maintenance contract |
| What is reserved | A specific unit (or N of a pooled quantity) | A provider's time slot, or a recurring visit entitlement |
| Capacity | 1 per unit, or pooled quantity | 1 per provider per slot, with working hours |
| Stock/Asset link | Asset (serialised) or Stock Item (pooled) | None (Service Item) or Timesheet |
| Billing basis | Per hour/day/night/week/month | Per hour/session/package, or monthly retainer |

Key design: **Rental Item** (what customers see) -> **Rental Unit** (the reservable thing) -> **Rental Booking** (a reservation of a unit for a time range). Services use *Rental Units of type Provider* (a person or a team). A maintenance contract is a **Rental Contract** that generates scheduled visits (bookings) and recurring invoices.

### Rental Type (template, drives behaviour)
Per business line: `Apartment`, `Hotel Room`, `Device`, `Storage Unit`, `Photographer`, `Maintenance Contract`.
Flags: `mode` (Resource/Service/Contract), `time_unit` (Hour/Day/Night/Month), `min_duration`, `max_duration`, `buffer_before`, `buffer_after` (cleaning/turnaround), `requires_deposit`, `requires_contract`, `requires_checkin`, `requires_return_inspection`, `allow_quantity`, `cancellation_policy`, `custom fields` (child table) such as bedrooms, megapixels, sqm, speciality.

## 3. DocTypes

Module `Rental`. Submittable docs use Frappe Workflow where noted.

### 3.1 Master data
**Rental Type** (above).

**Rental Item** (customer-facing listing; links to ERPNext `Item`)
- `item_code` (Link Item, auto-created: non-stock, service flag), `item_name`, `rental_type`, `description`, `images` (child), `category` (Tree: Rental Category), `location` (Link Rental Location), `capacity_people`, `amenities` (child: Rental Amenity), `rate_card` (Link Rental Rate Card), `is_published`, `route` (portal URL), custom attributes (child table `Rental Attribute Value`).

**Rental Unit** (the reservable thing)
- `unit_name`, `rental_item`, `unit_type` (Asset/Stock Pool/Provider/Space), `asset` (Link Asset), `employee` or `supplier` (Link, for providers), `warehouse`, `quantity_available` (pooled), `status` (Available/Occupied/Maintenance/Blocked/Retired), `location`, `parent_unit` (Tree, e.g. Building -> Floor -> Apartment), `working_hours` (Link Rental Schedule for providers).

**Rental Location** (branch, building, city; Tree; address, geo, timezone).

**Rental Schedule** with child **Rental Schedule Slot** (weekday, from, to) and holiday list for providers and seasonal closures.

**Rental Rate Card** with child **Rental Rate** rows
- `time_unit`, `rate`, `min_units`, `valid_from`, `valid_to`, `weekday_mask`, `season`, `customer_group`, `priority`.
- **Rental Charge**: cleaning fee, delivery, insurance; fixed or percent, per booking or per unit-time, tax template.

**Rental Cancellation Policy** with child rows (hours_before_start, refund_percent, fee).

**Rental Deposit Rule** (percent or fixed; refundable; held in a liability account).

**Rental Settings** (single): default accounts (deposit liability, rental income), default price list, grace period for late return, late fee rate, hold expiry minutes (default 15), auto-invoice toggle, portal toggles, payment gateway, timezone.

### 3.2 Transactions
**Rental Quotation** (optional; becomes Booking; can link ERPNext Quotation).

**Rental Booking** (submittable; workflow below)
- Header: `customer`, `contact`, `booking_type`, `status`, `source` (Portal/Desk/API/Phone), `from_datetime`, `to_datetime`, `all_day`, `rental_type`, `location`, `company`, `cost_center`, `currency`, `price_list`.
- Child **Rental Booking Line**: `rental_item`, `rental_unit` (auto-assigned or chosen), `qty`, `from/to` (override), `time_unit`, `units` (computed), `rate`, `discount_pct`, `amount`, `applied_rule`.
- Child **Rental Booking Charge**: extras and fees.
- Totals: `net_total`, `taxes_and_charges` (template), `grand_total`, `deposit_required`, `deposit_paid`, `balance`.
- Links: `sales_order`, `sales_invoice` (dynamic table), `contract`, `project` (services), `payment_entries`.
- Cancellation: `cancelled_on`, `cancellation_reason`, `refund_amount`.
- Hold: `hold_expires_on` (status Hold).

**Rental Contract** (submittable) wraps ERPNext `Contract` for signatures
- `customer`, `contract_type` (Fixed term / Evergreen / Maintenance plan), `start_date`, `end_date`, `auto_renew`, `renewal_notice_days`, `billing_interval` (Monthly/Quarterly/Yearly), `billing_amount`, `subscription` (Link Subscription), `erpnext_contract` (Link Contract), `terms` (Link Contract Template), `signed_by`, `signed_on`, `status`.
- Child **Rental Contract Item**: covered items/units/sites, with SLA fields (response_hours, visits_per_period).
- Child **Rental Visit Schedule**: planned visit date, assigned technician, linked booking/task, status.

**Rental Handover** (check-out/delivery/check-in; one doc per event)
- `booking`, `type`, `datetime`, `performed_by`, child **Rental Handover Item** (condition, photos, accessories checklist, meter readings), `customer_signature` (Signature field), `notes`.

**Rental Damage Report**: `booking`, `unit`, `description`, `photos`, `estimated_cost`, `charge_to_customer`, `deduct_from_deposit`, `sales_invoice`, `maintenance_request` (Asset Maintenance / Asset Repair).

**Rental Deposit** (ledger of a held deposit): `booking`, `amount`, `payment_entry`, `status` (Held/Partially Refunded/Refunded/Forfeited), `deductions` (child), `journal_entry`.

**Rental Block** (maintenance, owner use, blackout; reduces availability): `unit`, `from`, `to`, `reason`.

**Rental Waitlist Entry** (v2): customer, item, desired dates, notify flag.

### 3.3 Support
**Rental Availability Cache** (hidden, indexed): `unit`, `slot_start`, `slot_end`, `source_doc`, `source_type` (Booking/Block/Hold). A materialised view maintained by hooks for fast overlap queries.
Notifications use Frappe's built-in Notification doctype (no new doctype).

## 4. Core workflows

### 4.1 Availability and calendar
- Overlap rule: booking `[from, to)` conflicts with another active entry on the same unit when `from < other.to + buffer_after and to + buffer_before > other.from`.
- Source of truth: `Rental Availability Cache` rows written on Booking `on_update` (Hold/Confirmed/Checked Out) and Block save; removed on cancel or expiry. A `SELECT ... FOR UPDATE` on the unit row inside the transaction prevents races.
- Pooled quantity: sum of overlapping `qty` must be <= `quantity_available`.
- Providers: slots generated from `Rental Schedule` minus holidays minus existing entries.
- Desk calendar: Frappe Calendar view plus Gantt view with resource rows (units grouped by location), colored by status.
- API `frappe_rental.api.availability.search(item/type, from, to, qty, filters)` returns ranked free units with computed price.

### 4.2 Booking lifecycle (workflow on Rental Booking)
`Draft -> Hold -> Confirmed -> Checked Out -> Returned -> Closed`, plus `Cancelled` and `No Show`.
- Hold auto-expires via scheduled job after `hold_expiry_minutes`.
- Confirm requires: availability pass, deposit paid (if required), contract signed (if required).
- Submit creates Sales Order (and Project for services). Cancel triggers the policy engine.

### 4.3 Pricing rules
First match by priority, then combine discounts:
1. Unit-specific rate. 2. Item rate card by time unit (hour/day/week/month). 3. Seasonal and weekday modifiers. 4. Duration breaks (7 nights = 10% off, a month = flat monthly). 5. Customer group discount. 6. Coupon (ERPNext Pricing Rule / Coupon Code). 7. Extras and fees. 8. Taxes via Sales Taxes template.
Rounding modes: per started unit, pro-rata, or minimum charge. Pricing is a pure function `pricing.quote(booking_dict)` returning a line breakdown, so portal, API and desk share one implementation. `applied_rule` is stored per line for audit.

### 4.4 Deposits
- Required amount from Deposit Rule; collected as an ERPNext Payment Entry against the Customer into a **deposit liability account** (not income).
- Held until return inspection. Release: refund Payment Entry, or Journal Entry converting part to income (damage, late fee) and refunding the rest.
- Gateway pre-authorisation holds (Stripe) as an option in phase 3.

### 4.5 Recurring billing
- Rental Contract creates an ERPNext **Subscription** for evergreen and monthly rentals (storage, apartments, maintenance plans).
- Short-term bookings invoice once: deposit or prepayment first, balance at check-out. Long stays can bill monthly via scheduled job `billing.generate_due_invoices`.
- Late fees: scheduled job adds a charge line to the next invoice.

### 4.6 Contracts
- Template library (ERPNext Contract Template) with Jinja merge fields from booking/contract.
- Customer signs on the portal; the signed PDF attaches to the contract and booking.
- Maintenance contract: generates a visit schedule (for example quarterly); each visit becomes a Booking for a technician plus a Task; SLA breaches flagged on the dashboard. Renewal reminders at `renewal_notice_days`.

### 4.7 Check-in / out and returns
- Check-out: Handover doc with condition checklist, photos, signature; sets Booking -> Checked Out and records Asset Movement. Pooled stock uses Delivery Note or Stock Entry (Material Issue).
- Return: inspection compared with handover, late detection (`now > to + grace` adds a late charge), auto-create Damage Report if flagged; unit status goes to Maintenance/Cleaning/Available per rule.
- Hotels and apartments: check-in/out without stock movement; a housekeeping Task is created on check-out.

### 4.8 Damage
Damage Report -> estimate -> approve -> settle by deducting from deposit, invoicing, or writing off. Creates an Asset Repair / maintenance request and blocks the unit with a Rental Block.

### 4.9 Cancellation and refunds
Policy engine picks the tier by hours before start and computes fee and refund. Result is a Credit Note (Sales Invoice return) and/or refund Payment Entry. If we cancel (provider no-show), the refund is full and an alternative slot is offered.

## 5. ERPNext integration map

| ERPNext doc | How we use it |
|---|---|
| Item | One non-stock Item per Rental Item (rental income account, item group "Rentals"); service flag for services |
| Customer / Contact / Address | Booking customer; portal user links to Customer |
| Quotation | Optional link from Rental Quotation |
| Sales Order | Created on confirm; carries lines and deposit via Payment Schedule |
| Sales Invoice | Final billing, monthly rent, damage, late fee; credit notes for cancellations |
| Payment Entry / Payment Request | Deposits, prepayments, refunds, portal payments |
| Asset / Asset Movement / Asset Maintenance | Serialised devices, storage units and property as assets; handover moves; damage repairs |
| Subscription / Subscription Plan | Recurring rent and maintenance retainers |
| Contract / Contract Template | Legal text, e-signature, fulfilment tracking |
| Project / Task / Timesheet | Service delivery (photo shoot, maintenance visit); billable hours via Timesheet can feed an invoice |
| Stock (Warehouse, Bin, Stock Entry) | Pooled equipment or consumable counts (optional mode) |
| Employee / Supplier | Provider backing record, payroll or payout |
| Journal Entry | Deposit conversion and adjustments |
| Pricing Rule / Coupon Code | Reused for discounts where possible |
| Notification / Email Template / Print Format | Confirmations, reminders, invoices, handover sheets |

Extension approach: **custom fields via fixtures** on Sales Order, Sales Invoice, Asset, Item (`rental_booking`, `rental_item`, `is_rental`) and **doc_events hooks** for sync only. No core controller overrides.

## 6. Roles and permissions

| Role | Access |
|---|---|
| Rental Admin | Everything, settings, rate cards, policies |
| Rental Manager | Bookings, contracts, blocks, pricing overrides, approvals, reports |
| Rental Agent (Front Desk) | Create and modify bookings, handovers, returns; cannot edit rates or waive fees above a limit |
| Rental Provider | Sees only own schedule, visits and shoots (User Permission on Rental Unit/Employee); completes jobs, uploads deliverables |
| Rental Accountant | Invoices, deposits, refunds (read bookings) |
| Rental Customer | Portal only; own bookings via User Permission on Customer |

User Permission on Rental Location supports multi-branch. Field-level permlevel on `rate`, `discount_pct` and deposit waivers. Workflow transitions are role-restricted; approval is needed above a discount threshold.

## 7. Customer portal and website

Built with Frappe website routes, Web Forms and a light JS layer (keeps installation simple); published pages use `Rental Item.route`.
- `/rentals`: search by type, dates, guests/qty, location, price; list and map.
- `/rentals/<item>`: gallery, amenities, price calculator, availability calendar, reviews (v3).
- `/book`: select -> extras -> details -> sign contract -> pay deposit -> confirmation.
- `/my-bookings`, `/my-bookings/<id>`: status, documents, pay balance, request change, cancel (shows refund preview), download invoice and contract.
- `/my-contracts`: renewals, upcoming visits, request service.
- Guest checkout creates Customer and User on payment. Payments via Payment Request and any ERPNext gateway (Stripe, PayPal, Razorpay).
- Email/SMS/WhatsApp notifications via Notification doctype; reminders by scheduler.
- i18n and RTL ready (all strings `_()`), per-location timezone handling.

## 8. REST API (whitelisted methods, token auth)

Base: `/api/method/frappe_rental.api.<module>.<fn>`; standard `/api/resource/Rental Booking` also works with permissions.
- `GET availability.search` (type, item, from, to, qty, location, filters)
- `GET availability.calendar` (unit/item, month) -> day/slot map
- `POST pricing.quote` (items, dates, coupon) -> breakdown
- `POST booking.create_hold`, `booking.confirm`, `booking.modify`, `booking.cancel` (`preview=1` for refund calculation)
- `POST booking.checkout`, `booking.checkin`
- `GET booking.get`, `booking.list_mine`
- `POST payment.create_request`; webhook `payment.gateway_callback`
- `GET contract.get`, `POST contract.sign`
- Outbound events via Frappe Webhook doctype: `booking.confirmed`, `booking.cancelled`, `handover.completed`.
- Idempotency key on create calls; rate limiting on public endpoints (`frappe.rate_limiter`).

## 9. Architecture and folder layout

```
frappe_rental/
  pyproject.toml            # frappe v15, erpnext dependency
  frappe_rental/
    hooks.py                # doc_events, scheduler_events, fixtures, website routes
    modules.txt, patches.txt
    rental/                 # module "Rental"
      doctype/
        rental_type/ rental_item/ rental_unit/ rental_booking/
        rental_booking_line/ rental_contract/ rental_handover/ ...
      workspace/rental/rental.json
      dashboard_chart/ number_card/ report/
        availability_report/ occupancy_report/ revenue_by_item/ utilization/ overdue_returns/
      print_format/ notification/
    services/               # pure business logic (unit-testable)
      availability.py  pricing.py  deposit.py  cancellation.py
      billing.py  contract.py  handover.py
    api/                    # whitelisted endpoints
    integrations/           # erpnext.py (SO/SI/PE sync), payments.py
    tasks.py                # scheduler: expire holds, reminders, invoicing, late fees
    fixtures/               # custom fields, roles, workflows, rental type presets
    templates/              # portal pages and emails
    www/                    # rentals, book, my-bookings
    public/js, public/css   # calendar, availability widget
    tests/
  docs/
```

Principles: thin DocType controllers, thick `services/`; every cross-doc side effect idempotent; background work via `frappe.enqueue`; index on `(unit, slot_start, slot_end)` in the availability cache; datetimes stored in UTC and shown in the location timezone; no core overrides.

**Scheduler**: every 5 min expire holds; hourly reminders and overdue-return flags; daily invoices, contract renewals, visit bookings, late fees; weekly utilisation snapshot.

**Testing**: `FrappeTestCase` scenarios for overlap edge cases, DST, pricing matrices and deposit accounting; GitHub Actions CI with MariaDB and Redis, `bench run-tests`, `ruff` and pre-commit.

## 10. Phased roadmap

| Phase | Weeks | Deliverable | Milestone |
|---|---|---|---|
| 0 Foundations | 1-2 | Bench + CI, app skeleton, Rental Type/Item/Unit/Location, fixtures, roles | Installs on a fresh site |
| 1 Core booking MVP | 3-7 | Rental Booking, availability and overlap engine, calendar, time-unit pricing, Sales Order/Invoice sync, workspace, Device and Apartment types | Staff can book and invoice a device or apartment end to end |
| 2 Money and operations | 8-12 | Deposits, cancellation policies, handover/return, damage, Asset integration, late fees, reports and dashboard | Full lifecycle with deposit refund |
| 3 Portal and payments | 13-17 | Website search, booking flow, payments, my-bookings, notifications, REST API v1 | Customer self-service booking live |
| 4 Services and contracts | 18-23 | Provider schedules (photographers), Project/Timesheet, Rental Contract, Subscriptions, visit scheduler, e-sign | Maintenance contracts and photographer bookings |
| 5 Hotels and storage | 24-28 | Housekeeping, room types, storage billing and access codes, waitlist, multi-location | Hotel and storage templates |
| 6 Hardening | 29-32 | Performance, security review, docs, demo data, marketplace packaging | v1.0 release |

Suggested team: 1-2 Frappe developers, 1 part-time front-end/portal developer, 1 functional ERPNext consultant. Phases 0-3 give a sellable MVP.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Double booking from races | Row lock on unit, cache table checked in a transaction, concurrency tests |
| Timezone and DST errors | UTC storage, location timezone, explicit DST tests |
| Generic model becomes confusing | Rental Type templates hide irrelevant fields; ship opinionated presets |
| Deposit accounting mistakes | Dedicated liability account, accountant review of JE templates, tests |
| ERPNext upgrade breakage | No core overrides, hooks and custom fields only; CI against latest v15 |
| Pricing complexity | Single pure `quote` function, rule audit trail, table-driven tests |
| Portal performance on large inventory | Availability cache, indexes, paginated search, Redis caching |
| Scope creep (channel managers, mobile) | Explicit non-goals; revisit after v1.0 |
| Payment and PII compliance | Gateway-hosted payment, no card data stored, Frappe privacy tools |

## 12. Decisions needed from the owner

1. **Launch verticals**: which two rental types first (recommended: Device and Apartment, then Photographer)?
2. **Deposits**: liability account with manual refund (simple) or gateway pre-authorisation (phase 3+)?
3. **Portal**: Frappe website pages (recommended) or a separate Vue frontend?
4. **Market**: country, currency, tax regime and payment provider.
5. **Multi-company or branches** from day one, or a single company first?
6. **Distribution**: private app for one business, or a marketplace product (affects multi-tenancy polish)?
