# Resolved open decisions (answers to `PLAN.md` section 12)

The owner asked for the best choices for the app. These are the defaults; each can be changed later without redesign.

1. **Launch scope**: the generic engine (D1). Acceptance presets in order: Device, Apartment, Photographer (service), then Maintenance contract, Hotel room, Storage.
2. **Deposits**: liability account with manual or one-click refund in v1 (D5). Gateway pre-authorisation holds are an optional adapter in a later phase.
3. **Frontend**: Frappe UI (Vue 3 + `frappe-ui`) for staff app and customer booking flow (D2). Public item pages are also rendered server-side by Frappe website routes for SEO and speed, then hand over to the Vue booking flow. Desk stays for setup doctypes.
4. **Market**: market-neutral. Multi-currency, per-type tax templates, i18n and RTL (Arabic ready), per-location timezone. Payments go through ERPNext Payment Request and Payment Gateway, so any gateway works; adapters built in order: Stripe, then a regional gateway chosen by the first customer (for example Paymob in Egypt). No country-specific logic in core.
5. **Multi-company and branches**: supported in the data model from day one (`company` on every transaction, Location belongs to a Company, User Permissions by Location and Company). The UI defaults to a single company so small users see no extra fields.
6. **Distribution**: built as a reusable product, not a one-off. Licence GPL-3.0 (matches Frappe and ERPNext, allows Marketplace listing). No hard-coded business names, accounts or item types; install creates editable defaults.

## Technical defaults
Frappe v15 and ERPNext v15; Python 3.11; MariaDB 10.6; Redis. Developer tooling: `bench`, `ruff`, pre-commit, GitHub Actions CI. Tests with `FrappeTestCase`; frontend with Vite and `frappe-ui`. Semantic versioning, `develop` and `version-15` branches. Frappe Cloud compatible (no custom system packages).

## Updated roadmap (replaces `PLAN.md` section 10)

| Phase | Weeks | Deliverable |
|---|---|---|
| 0 Foundations | 1-2 | App skeleton, CI, Rental Type, Item, Unit (with identification and Asset/Serial links), Location, roles, accounting defaults |
| 1 Core booking | 3-9 | Booking, availability and overlap engine, pricing rules, calendar, Sales Order and Invoice sync, Frappe UI staff app shell (list, detail, calendar, availability) |
| 2 Money and operations | 10-16 | Billing plans and schedules (D6), deposits, cancellation policy, handover and return with scan, damage, Asset Movement and stock entries, late fees, allocation-to-availability integration, reports and dashboard |
| 3 Customer website and payments | 17-22 | Item pages, availability calendar, booking flow, payments, my bookings, notifications, REST API v1 |
| 4 Contracts and services | 23-29 | Terms library, templates, amendments, e-signature, allocations and call-off bookings (D7), Subscriptions, provider schedules, Project and Timesheet, visit scheduler |
| 5 Extensions | 30-35 | Metered usage, consolidated invoices, housekeeping, waitlist, multi-location polish, extra presets |
| 6 Hardening and release | 36-40 | Performance, security review, docs, demo data, Marketplace packaging, v1.0 |

Phases 0-3 give a sellable MVP (about 22 weeks) with one or two developers; the Frappe UI app adds roughly 4 weeks compared with desk-only.
