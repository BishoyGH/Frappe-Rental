# Task backlog for Claude Code

Work top to bottom. One task = one PR. Each task lists what to build (**Build**), how we know it is done (**Done when**), and **Needs** (earlier tasks). Rules are in `CLAUDE.md`. Docs referenced: P = `PLAN.md`, D = `DECISIONS.md`, F = `FINAL_DECISIONS.md`, I = `INVOICING.md`, C = `CONTRACTS.md`, V = `COMPATIBILITY.md`.

**Every task must pass on Frappe/ERPNext v15 and v16** (V). "Tests pass" below means the CI matrix on both versions.

## Phase 0: Foundations

- [x] **T00A Verify version requirements.** Build: read the official Frappe and ERPNext release notes and install docs for v15 and v16; create `ci/versions.yml` (per major: frappe and erpnext branch, Python, Node, MariaDB, Redis) and a short table in `docs/DEV.md`; decide the exact dependency bounds for `pyproject.toml`. Done when: every value cites its source link in a comment; no other file hard-codes these versions. Needs: none.
- [ ] **T00B Dual-version dev environment.** Build: scripts and docs to create two benches (v15 and v16) side by side (`scripts/bench-setup.sh <15|16>`), optional devcontainer, helper to run tests on both. Done when: a fresh machine can run `scripts/bench-setup.sh 15` and `16` and both install ERPNext. Needs: T00A.
- [ ] **T01 Repo and app skeleton.** Build: app layout (`pyproject.toml` with bounds from T00A, `hooks.py`, module Rental, `modules.txt`), GPL-3.0 licence, README stating supported versions with install steps for each, `.gitignore`, `develop` branch. Done when: the app installs and `bench migrate` is clean on v15 and v16 benches. Needs: T00B.
- [ ] **T00C Compat layer.** Build: `frappe_rental/compat/` (`__init__.py` with `frappe_version()`, `IS_V15`, `IS_V16`; `frappe.py`, `erpnext.py`, `ui.py` stubs), docstring convention, test that imports every module on both versions, and a lint rule (ruff banned-api or a test) forbidding direct version checks outside `compat`. Done when: tests pass on both; the lint check fails on a sample violation. Needs: T01.
- [ ] **T02 Tooling and CI.** Build: ruff and pre-commit; GitHub Actions matrix for v15 and v16 (MariaDB, Redis, versions from `ci/versions.yml`), jobs for lint, tests, frontend build placeholder, nightly job for oldest supported minors and an allowed-failure job for the next major; PR and issue templates (issue asks for Frappe/ERPNext versions); deprecation warnings surfaced and failing for our code. Done when: both matrix legs are required checks and green on an empty test. Needs: T01.
- [ ] **T03 Test harness.** Build: shared test helpers (customer, item, company defaults, rental type, unit, booking factories) in `tests/utils.py`, using compat helpers where ERPNext differs. Done when: a sample test creates a full fixture set in under 5 s on both versions. Needs: T02, T00C.
- [ ] **T04 Rental Settings and install defaults.** Build: Rental Settings single doctype; `after_install` creates Item Group `Rentals`, accounts (Rental Income, Customer Deposits (Rental), Late Fee Income, Damage Recovery, Deposit Forfeiture Income), warehouse `Rented Out`, Accounting Dimension `Rental Item Type`, roles (P section 6). Done when: install is idempotent on both versions and reinstall creates no duplicates; test asserts all records. Needs: T03.
- [ ] **T05 Rental Location.** Build: Tree doctype with company, address, timezone, cost center auto-create. Done when: User Permission by Location works in a test. Needs: T04.
- [ ] **T06 Rental Type.** Build: doctype with booking mode, billing units, durations, buffers, required steps, deposit and cancellation links, tax template, identification mode, custom fields child table that creates real Custom Fields on Item/Unit/Booking; preset loader (JSON) for Device, Apartment, Photographer, Maintenance, Hotel room, Storage, Vehicle, Event gear. Done when: a type with two custom fields adds them to Rental Item and shows in forms on both versions; presets install from a button. Needs: T04.
- [ ] **T07 Rental Item.** Build: doctype linked to ERPNext Item (auto-create, rental item group, income account from type), images, amenities, attributes, publish flag and route. Done when: saving creates or syncs the Item; unpublish hides it; sync tests both ways. Needs: T05, T06.
- [ ] **T08 Rental Unit and identification.** Build: doctype with unit code series, barcode/QR generation, serial_no, batch, asset link, external_ids child, parent unit tree, status, location; validation by identification mode (D4). Done when: modes None, Asset, Serial, Batch, Pooled each validated; lookup by any identifier API works; label print format exists. Needs: T07.
- [ ] **T09 Roles, permissions, workspace.** Build: permissions for all doctypes so far, Rental workspace with shortcuts, number card stubs. Done when: permission matrix test per role (admin, manager, agent, accountant, customer, provider). Needs: T08.

## Phase 1: Core booking

- [ ] **T10 Rate card and charges.** Build: Rental Rate Card, rates (unit, season, weekday mask, customer group, priority), Rental Charge, deposit rule, cancellation policy doctypes. Done when: CRUD and validation tests (no overlapping same-priority rules). Needs: T07.
- [ ] **T11 Pricing service.** Build: `services/pricing.py` pure `quote()` implementing P 4.3 (all billing units, tiers, seasons, rounding modes, discounts, charges, taxes) plus `rental_pricing_hooks`. Done when: table-driven tests cover at least 40 cases including DST and month-end; no database writes. Needs: T10.
- [ ] **T12 Rental Booking doctype.** Build: Booking, Booking Line, Booking Charge, statuses, totals via pricing service, company/cost center, validation of type rules. Done when: draft bookings price correctly in forms and API. Needs: T11, T08.
- [ ] **T13 Availability cache and overlap engine.** Build: Rental Availability Cache, `services/availability.py` (exclusive, pooled, capacity, open-ended, buffers), row locking, Rental Block doctype. Done when: concurrency test with parallel bookings never double-books; edge tests (adjacent slots, buffers, DST, pooled sums). Needs: T12.
- [ ] **T14 Hold, confirm, cancel lifecycle.** Build: workflow states, hold expiry job, confirm guards, submit/cancel hooks writing the cache. Done when: expired holds release units; cancel frees units; tests per transition. Needs: T13.
- [ ] **T15 Availability search API.** Build: `api.availability.search` and `calendar` per P section 8 with ranking and price. Done when: correct free units across mixed types; 5,000 units search under 300 ms. Needs: T13.
- [ ] **T16 ERPNext sync: Sales Order and Invoice.** Build: create Sales Order on confirm, one-off Sales Invoice, custom field fixtures on SO/SI/Asset/Item, idempotent sync, cancellation reversal; any field or behaviour difference between ERPNext v15 and v16 goes through `compat.erpnext`. Done when: totals and taxes match booking; reruns create no duplicates; passes on both versions. Needs: T14.
- [ ] **T17 Frontend scaffold.** Build: `frontend/` Vite + Vue 3 + frappe-ui (versions pinned to work on both Frappe majors, Node from `ci/versions.yml`), served at `/rental`, login and role gate, sidebar shell like the mockups, CI build and Playwright smoke on both matrix legs. Done when: shell loads for a logged-in user and redirects others on v15 and v16. Needs: T09, T02.
- [ ] **T18 Staff app: bookings list and detail.** Build: list with filters/group/sort/columns, detail page with tabs, side panel (summary, deposit, linked docs, activity), create flow. Done when: matches mockups; Playwright smoke passes on both versions. Needs: T17, T14.
- [ ] **T19 Staff app: calendar and availability.** Build: resource timeline with drag create/move, availability search page, quick book. Done when: conflicts rejected in UI; Playwright test. Needs: T15, T17.
- [ ] **T20 Staff app: setup screens.** Build: Item types builder (custom fields UI), Items, Units, Customers list/detail. Done when: the Boat example can be defined end to end in the UI. Needs: T17, T06, T08.
- [ ] **T21 Phase 1 acceptance.** Build: scenario tests and a demo-data command for Device and Apartment presets (book, invoice end to end); update `docs/DEV.md`. Done when: scripted scenario passes in CI on both versions. Needs: T16, T18, T19, T20.

## Phase 2: Money and operations

- [ ] **T22 Billing plan and schedule.** Build: Rental Billing Plan, Billing Schedule, generator for all frequencies, timings, alignment, proration (I). Done when: the quarterly device example produces 4 rows of 3,600; property tests for proration and month-end. Needs: T16.
- [ ] **T23 Invoicing job.** Build: daily job creating Sales Invoices from due rows, idempotent locking, grouping options, email, regeneration of un-invoiced rows on change, credit notes for invoiced adjustments. Done when: reruns never double-bill; tests for extension, shortening, early return. Needs: T22.
- [ ] **T24 Billable events.** Build: Billable Event queue (late fee, damage, delivery, extension, termination fee) joining next invoice on correct income accounts. Done when: events invoiced once on correct accounts. Needs: T23.
- [ ] **T25 Deposits and accounting.** Build: Rental Deposit, collection via Payment Entry, settlement (refund, apply to charges via Journal Entry, forfeit), accounts per D5, deferred revenue option; compat helpers for any Payment Entry or accounting-field difference. Done when: GL entries asserted in tests for each settlement path on both versions. Needs: T16.
- [ ] **T26 Cancellation engine.** Build: policy tiers, fee and refund calculation, preview API, credit notes, provider-cancel full refund. Done when: tier boundary tests; preview equals actual. Needs: T25, T23.
- [ ] **T27 Handover and return.** Build: Rental Handover, checklist items, photos, signature, scan input, late detection, unit status rules; Asset Movement and stock entries (Material Issue/Receipt to `Rented Out`) per identification mode, with Asset and Serial No behaviour differences isolated in `compat.erpnext`. Done when: serial history shows customer per serial; asset location updates; tests per mode on both versions. Needs: T08, T14.
- [ ] **T28 Damage report.** Build: Damage Report, estimate/approve, settle (deposit, invoice, write-off), Asset Repair link, auto Rental Block. Done when: settlement paths tested with GL assertions. Needs: T27, T25.
- [ ] **T29 Staff app: handover/return, billing, deposits.** Build: scan-first handover screens, Billing tab with schedule editing, deposit and damage panels. Done when: matches mockups; Playwright flows. Needs: T17, T22, T27, T28.
- [ ] **T30 Reports and dashboard.** Build: availability, occupancy, utilisation, revenue by type/branch, overdue returns, unit history, per-asset ROI; dashboard screen with KPI cards and charts. Done when: report totals reconcile to GL in tests. Needs: T23, T27.
- [ ] **T31 Notifications.** Build: Notification templates for confirmation, reminders, overdue, invoice, deposit; event hooks and webhooks (D3). Done when: events fire once; webhook payload documented. Needs: T14.
- [ ] **T32 Phase 2 acceptance.** Build: scenario suite for full lifecycle (quarterly device, hotel stay, damage with deposit refund) and accountant review checklist. Done when: all pass on both versions; GL screenshots in docs. Needs: T26 to T31.

## Phase 3: Customer website and payments

- [ ] **T33 REST API v1.** Build: `api/booking`, `pricing`, `payment`, `contract` endpoints per P section 8, idempotency keys, rate limiting, OpenAPI spec file. Done when: contract tests for every endpoint including permission failures. Needs: T26.
- [ ] **T34 Public item pages.** Build: server-rendered `/rentals` and `/rentals/<item>` with SEO metadata, filters, gallery, price calculator, availability calendar; template features limited to what both versions support. Done when: Lighthouse performance 90+ on item page on both versions; tests. Needs: T33.
- [ ] **T35 Customer booking flow.** Build: Vue flow (select, dates, extras, details, sign, pay), guest checkout creating Customer and User. Done when: Playwright end-to-end booking as guest and as returning customer on both versions. Needs: T34.
- [ ] **T36 Payments.** Build: Payment Request integration, Stripe adapter, webhook handler, deposit collection, failure and retry paths; verify payment-gateway behaviour on both versions. Done when: sandbox payment test; webhook replay is safe. Needs: T35, T25.
- [ ] **T37 My bookings portal.** Build: list/detail, pay balance, change and cancel with refund preview, documents download. Done when: customer sees only own data (permission tests). Needs: T35.
- [ ] **T38 Phase 3 acceptance and security pass.** Build: end-to-end suite, rate limit and permission review, dependency audit. Done when: no high findings; MVP tag `v0.1.0`. Needs: T36, T37.

## Phase 4: Contracts and services

- [ ] **T39 Clause library and templates.** Build: Rental Clause, Terms Template, Jinja rendering, language/RTL, preview (C). Done when: render tests with merge fields; template versioning. Needs: T33.
- [ ] **T40 Rental Contract core.** Build: contract doctype with structured terms, lifecycle workflow, snapshot at signing, amendments; ERPNext Contract link via compat if fields differ. Done when: workflow tests; snapshot unchanged after template edit. Needs: T39, T22.
- [ ] **T41 E-signature.** Build: portal signing (typed/drawn, optional OTP), counter-signature, signed PDF, audit fields, reminders. Done when: signed contract immutable; tests. Needs: T40, T37.
- [ ] **T42 Allocations.** Build: allocation rows (unit, category, quantity, capacity, provider time), cache integration, over-allocation guards, swap/add/release with effective dates and billing regeneration. Done when: exclusive allocation blocks calendar; swap tested end to end. Needs: T40, T13.
- [ ] **T43 Call-off bookings and entitlements.** Build: bookings against allocations decrementing capacity/hours, inheriting rates and terms, overage billing. Done when: allowance and overage tests. Needs: T42.
- [ ] **T44 Renewal and termination.** Build: auto-renew, notice reminders, indexation, termination with fee, closure checklist. Done when: scheduled-job tests with frozen time. Needs: T40, T24.
- [ ] **T45 Provider scheduling.** Build: Rental Schedule, holidays, slot generation, provider role view, Project/Task/Timesheet link and billing from timesheets. Done when: photographer booking and visit scenarios pass. Needs: T13, T33.
- [ ] **T46 Maintenance visits.** Build: visit schedule generation from contract, technician assignment, completion, SLA tracking. Done when: quarterly HVAC scenario passes. Needs: T44, T45.
- [ ] **T47 Staff and portal contract screens.** Build: contract tabs (overview, terms, allocations, billing, bookings), portal `/my-contracts`. Done when: matches mockups; Playwright flows. Needs: T41, T42, T46.
- [ ] **T48 Phase 4 acceptance.** Build: scenario suite (12-month device quarterly billing with swap, photographer retainer, maintenance plan renewal). Done when: all pass on both versions; tag `v0.2.0`. Needs: T43 to T47.

## Phase 5: Extensions

- [ ] **T49 Metered usage.** Build: readings at handover/API, allowance and overage billing. Done when: tests. Needs: T24.
- [ ] **T50 Consolidated invoices.** Build: per-customer per-period grouping with per-line references. Done when: totals tests. Needs: T23.
- [ ] **T51 Housekeeping and turnaround.** Build: tasks on check-out, unit status automation, buffer integration. Needs: T27.
- [ ] **T52 Waitlist and substitutions.** Build: waitlist notify, substitute suggestions on conflict. Needs: T15.
- [ ] **T53 Additional presets and import.** Build: CSV import for items/units/customers with identifiers; more presets. Needs: T08.
- [ ] **T54 Gateway adapter 2 and pre-authorisation (optional).** Build: regional gateway adapter, card hold/capture for deposits. Needs: T36.
- [ ] **T54b Postgres support (optional).** Build: enable the Postgres CI leg, fix SQL portability issues. Done when: tests pass on Postgres for both versions. Needs: T38.

## Phase 6: Hardening and release

- [ ] **T55 Performance.** Build: indexes, query review, caching, load test 100k bookings on both versions. Done when: targets in `docs/DEV.md` met.
- [ ] **T56 Security review.** Build: permission audit, input fuzz tests on public endpoints, secrets and PII review, dependency scan in CI; re-check that v16-specific permission or API changes are covered by tests.
- [ ] **T57 Accessibility and i18n.** Build: WCAG pass on website, Arabic translation file and RTL check, translation extraction in CI.
- [ ] **T58 Documentation.** Build: user guide per role, admin setup guide, API reference, accounting guide (D5), upgrade notes, supported-versions page.
- [ ] **T59 Demo site and data.** Build: `bench rental-demo` command, seeded demo with all presets; works on both versions.
- [ ] **T60 Release.** Build: version tags, changelog, Marketplace and Frappe Cloud packaging checks on both versions, upgrade/migration test from `v0.2.0` on both, promote or retire the next-major CI job. Done when: `v1.0.0` tagged and installs clean on v15 and v16.

## Standing tasks (any time)
- Keep `docs/TASKS.md`, mockups and docs in sync with what is built.
- Bugs get their own `fix/` PR with a failing test first, reproduced on both versions.
- Review the next-major (v17) CI job weekly once it exists; open a task for each new break.
- Remove compat shims when their removal condition is met.
