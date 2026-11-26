# Changelog

Versions follow semantic versioning. Schema changes ship as DocType JSON, so `bench migrate` is the whole upgrade.

## 1.0.0

First stable release. Runs unchanged on Frappe and ERPNext v15 and v16.

- Rental engine: types, items, units, rate cards and seasons, availability with holds and no double booking, pricing with charges, deposits, cancellation policies, handover and return with damage reports, housekeeping, metering, waitlist, blocks.
- ERPNext link: Sales Invoices, Payment Entries and deposit journal entries; invoicing for bookings, contracts and schedules.
- Contracts: terms templates and clauses, e-signature with email code, countersign and signed PDF, billing plans, allocations and call-off, visits with service levels, amendments, renewal.
- Staff app (Vue): bookings, calendar, availability, contracts, handovers, setup screens, settings with staff alerts.
- Customer site: public rentals pages, booking flow with guest checkout, online payment through Stripe with a signed webhook, My bookings and My contracts.
- Staff alerts: in-app alerts by role for damage, SLA breaches, overdue returns and housekeeping, with optional email; rules in Rental Settings.
- Security: guest endpoints allowlisted and rate limited, state changes POST only, fuzz tests, dependency audit and secrets scan in CI.
- Arabic translation and right-to-left layout.

## 0.2.0

Contracts, billing plans, call-off allocations, service visits, e-signature and renewals (phase 4).

## 0.1.0

Core rental engine, staff app, public site, payments and My bookings (phases 1 to 3).
