# Decisions (override `PLAN.md` where they differ)

## D1. Rent anything
No fixed list of verticals. Every rentable thing is defined by a user-created **Rental Type** (called "Item type" in the UI) with its own booking rules (resource or service, billing units, min/max duration, buffers, deposit, cancellation policy, required steps) and **custom fields** added in the UI (Frappe Custom Field / child table, no code). The types named in `PLAN.md` (apartment, hotel room, device, storage, photographer, maintenance contract) ship only as **presets** to copy from, plus examples such as vehicle, boat and event gear. The first release is the generic engine, not a set of verticals. Phase 1 is validated with two presets (Device and Apartment) only as acceptance tests.

## D2. Frappe UI look
The staff app and customer website follow the **Frappe UI** design language (as in Frappe CRM and Helpdesk): gray sidebar with workspace switcher, compact list views, badges, tabbed detail pages with a side panel.
Implementation: a Vue 3 + `frappe-ui` single-page app served at `/rental` (staff, role-gated) and a public Vue/website app at `/rentals` for customers, both talking to the whitelisted REST API in `PLAN.md` section 8. Desk (standard Frappe forms) stays available for setup DocTypes such as Rate Card and Settings. This adds a `frontend/` folder (Vite + frappe-ui) to the layout in section 9 and about 4 weeks to phases 1 and 3.

## D3. Flexibility rules
Anything a business may want to vary is configuration, not code:
- **Rental Settings and Rental Type** hold every toggle (deposit, contract, handover, inspection, buffers, hold time, late fees, tax template, accounts).
- **Per-type workflow**: the booking lifecycle states are fixed internally, but each Rental Type chooses which steps are required (skip Hold, Handover, Return inspection, Contract).
- **Pricing is rule rows**, not hard-coded: any billing unit (minute, hour, day, week, month, year, per use, per km via a metered quantity), tiers, seasons, weekday masks, customer groups, and a custom Python hook (`rental_pricing_hooks` in `hooks.py`) for exotic cases.
- **Custom fields and child tables** on Item type, Item, Unit and Booking, shown in list, form, portal and API automatically (field metadata drives the UI).
- **Document events** (`booking_confirmed`, `handover_done`, `returned`, `cancelled`, `invoice_due`) are exposed as hooks and as Frappe Webhooks and Notifications, so integrations need no fork.
- **Booking modes** per type: exclusive unit (one booking at a time), pooled quantity, capacity (seats/guests), or open-ended (no end date, billed until closed).

## D4. Assets, serial numbers and identification
A **Rental Unit** is the physical or logical thing that gets booked, and it carries identity:
- `unit_code` (auto-series, unique), `barcode` / `qr_code` (generated, printable label), `serial_no` (ERPNext Serial No link when serialised), `batch_no` (optional), `asset` (ERPNext Asset link), `external_ids` (child table: type + value, e.g. IMEI, plate number, MAC, licence, RFID tag, so any identifier works).
- **Identification modes** per Item type: `None`, `Asset` (one Asset per unit), `Serial No` (stock item with serial numbers), `Batch`, `Pooled quantity`. This covers a camera (Serial No or Asset), a building or vehicle (Asset), a tent (pooled), and a service provider (no stock identity).
- **Asset** use: the unit links to an ERPNext Asset; rental income can be tracked per asset through a Cost Center or Accounting Dimension (`Rental Unit`) on invoices; depreciation stays in ERPNext's Asset module; repairs use Asset Repair and Asset Maintenance; check-out/in write **Asset Movement** (issue/receipt) with a rental location; asset status (In Use, In Maintenance) is synced so the same record answers "where is it" for both modules.
- **Serial No** use: for stock items, handover scans or selects the serial, creates a Delivery Note or Stock Entry (Material Issue to a "Rented Out" warehouse), and the return creates a Stock Entry (Material Receipt) back, so stock-ledger history shows exactly which serial was with which customer.
- **Scan-first workflows**: handover and return screens accept barcode, QR or serial input, and the portal/API can look up a unit by any identifier.
- **Rental Unit History** (read-only child list or report): every booking, handover, damage and repair for a unit, searchable by any identifier.

## D5. Accounting choices
Chosen to stay inside standard ERPNext accounting and avoid custom ledger logic.
1. **Revenue**: rental income is recognised on **Sales Invoices**, with a dedicated income account per Item type (default `Rental Income`, overridable per type), set through the Item's income account. Services (photographer, maintenance) use their own income account.
2. **Deposits**: a **liability account** `Customer Deposits (Rental)` (not income). Collected by Payment Entry with the Customer as party (using the "Advance" mechanism or a dedicated account). Never offset against invoices automatically; the settlement step makes the choice explicit.
3. **Deposit settlement**: refund by Payment Entry (Pay), or apply to charges (late fee, damage) with a Journal Entry: Dr Customer Deposits, Cr Rental income / Damage recovery, then refund the remainder. Forfeited deposit is recognised as income (`Deposit Forfeiture Income`).
4. **Prepayments and long stays**: for bookings billed in advance, invoice at confirmation and use **Deferred Revenue** (Item "Enable Deferred Revenue", service start/end dates) so income is recognised over the rental period. Monthly rentals bill each month through Subscription, no deferral needed.
5. **Recurring billing**: ERPNext **Subscription** generates Sales Invoices; Rental Contract stores the plan, so proration and renewals follow standard ERPNext behaviour.
6. **Tax**: one Sales Taxes and Charges template per Rental Type (e.g. VAT on rentals, accommodation tax for hotel rooms, exempt residential leases). Deposits are outside the scope of VAT while held; tax applies when converted to income.
7. **Cancellation and refunds**: cancellation fees are invoiced and any refund is paid by Payment Entry; if an invoice already exists, a **Credit Note** (return invoice) is issued for the refunded part.
8. **Damage and late fees**: separate invoice lines on their own income accounts (`Damage Recovery`, `Late Fee Income`) so reports show them apart from rental revenue.
9. **Cost tracking**: **Cost Center** per location and an **Accounting Dimension** `Rental Item Type` on invoices, so revenue and cost by type and branch come from standard reports (P&L by dimension).
10. **Asset economics**: depreciation and repair costs stay on the Asset; a report joins asset cost and rental revenue per unit (utilisation, revenue, cost, ROI).
11. **Sub-rentals and owner payouts** (property managed for owners): optional later; the Supplier-side is a Purchase Invoice or Journal Entry created from a commission rule. Not in v1.
12. **Multi-currency**: booking uses the Customer's currency and price list; exchange gain/loss is handled by ERPNext on Payment Entry. Deposits are held in the currency received.
13. **Period closing**: a booking never changes posted invoices; changes after invoicing create adjustment invoices or credit notes.
14. **Defaults created at install** (editable): accounts above, Item Group `Rentals`, Warehouse `Rented Out`, Accounting Dimension, Cost Center per Location, tax templates.

Mockups: https://claude.ai/artifact/GWrCpQ4YQmxYKq34oEZmjY

## D-branching (2026-11-25)
Foundation tasks T00A to T00C are stacked as one commit per task on a single branch with one PR, because no `develop` branch exists yet and push access is limited to that branch. Per-task PRs resume once `develop` exists (T01).

## D-accounting-dimension (2026-11-25)
The `Rental Item Type` Accounting Dimension is created in T06 together with the Rental Type DocType it points to, not in T04.

## T14 booking lifecycle (2026-11-26)
- A hold is a saved draft with status Hold; confirming is submitting. Types use the hold step by default (`requires_hold` = 1).
- An expired hold returns to Draft (not Cancelled) so staff can hold it again; a cancelled hold keeps docstatus 0 with status Cancelled.
- Until a Rental Contract doctype exists, `requires_contract` checks a linked ERPNext Contract with `is_signed`.

## D-ui-tests (2026-11-26)
Browser tests use **Playwright**, not Cypress. Frappe core ships Cypress tests, but they target its own desk and test site; Playwright runs headless in CI without extra services, works the same against v15 and v16 benches, and is what `docs/COMPATIBILITY.md` already names for the smoke suite. The harness is task T16B; later UI tasks add specs to it.

## T16 ERPNext sync (2026-11-26)
- Each booking line is one Sales Order Item with qty 1 and rate = line amount, so ERPNext totals equal the booking's exactly; qty and period go in the description. Charges become items (the Rental Charge's Item, else an auto-made service Item).
- The Sales Order is created and submitted on confirm. The one-off Sales Invoice comes from it on confirm when `auto_invoice` is on, otherwise via `api.booking.make_invoice`.
- Cancel: an unpaid invoice is cancelled, a paid one gets a credit note (the Sales Order is then closed, not cancelled); an uninvoiced Sales Order is cancelled.
- Custom fields are created with `create_custom_fields` on install and migrate instead of fixture files, so they stay idempotent and versioned in code.

## D-phase-prs (2026-11-26)
From T19 on, work is delivered as one pull request per phase, with one commit per task inside it. The PR opens when the phase's last task is done and CI is green on v15 and v16.

## T19 calendar (2026-11-26)
- The calendar moves only draft and held bookings. A confirmed (submitted) booking changes through amendment, which a later task adds.
- A move to another unit is allowed only for a one-item booking and only to a unit of the same item.
- Conflicts are checked in the browser for instant feedback and again on the server, which has the final word.

## D-one-pr (2026-11-26)
All remaining tasks go into one pull request, so Bishoy can run and debug the app from a single branch. It stays a draft while work continues, with one commit per task. This replaces D-phase-prs.

## T20 setup screens (2026-11-26)
- The SPA edits setup records through `api.setup.get_records/get_record/save_record`, which allow only the doctypes and fields each screen names. The item type's custom fields are the only extra keys an Item or Unit form may write.
- Playwright blocks `socket.io` and `favicon.ico` requests. `bench serve` has no socket.io server and is built without website assets, and its error page for those requests leaves a database transaction open. That open transaction blocks the schema change behind a new custom field. Production serves both, so only the test harness needs this.

## D-deposit-journal (2026-11-26, T25)
Deposits move by **Journal Entry**, not Payment Entry. A Payment Entry for a Customer needs a receivable account, and its advance-account options differ between ERPNext v15 and v16. A Journal Entry posts straight to the `Customer Deposits (Rental)` liability on both versions. Each entry carries `rental_deposit` and is listed on the Rental Deposit. Applying a deposit to an invoice credits the customer's receivable against that invoice, so its outstanding amount drops as it would after a payment. VAT on applied or forfeited amounts (D5.6) is not posted automatically yet.

## T33 REST API v1 (2026-11-26)
- Endpoints stay whitelisted methods under `frappe_rental.api.*` (PLAN section 8); the OpenAPI file documents them by hand, since Frappe does not generate one.
- Idempotency keys live in Redis for 24 hours, scoped by user, method and key; a reused key with other arguments returns 409. No new doctype: a lost key only means a retry runs again.
- Rate limits use `frappe.rate_limiter.rate_limit` (same signature on v15 and v16), 60 create calls per minute per IP.
- Payments go through ERPNext Payment Request (`compat.erpnext.make_payment_request`); the gateway's callback is handled by ERPNext and the gateway app, so there is no rental callback endpoint.

## T35: customer booking flow runs ERPNext side effects as Administrator
Customers (Website Users) have no desk permissions on Rental Booking, Sales Order or Contract, and ERPNext
controllers check the session user's permissions deep inside (item details, price lists). The flow
therefore checks ownership first (`checkout.own_booking`: the booking's customer must be one the user acts
for) and then inserts, holds, signs and submits inside `checkout._as_system()`, which restores the session
user afterwards. Guest sign-up refuses an email that already has an account, so nobody can book as someone
else by typing their address. The flow lives in the staff SPA bundle as public routes rather than a second
bundle, to keep one build.
