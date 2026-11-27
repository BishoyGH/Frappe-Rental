# Security review (T38)

Checked at the end of phase 3. Re-run before each release (T56 goes deeper).

## Guests

Only six methods allow guests, and each is rate limited per IP: `checkout.extras`, `checkout.start`, `public.items`, `public.quote`, `public.calendar` and the payment webhook (`payment.stripe_webhook`, which verifies an HMAC signature with a 5 minute window). `tests/test_security.py` fails if another guest method appears or one loses its limit.

## Customers

Customers are Website Users with no desk rights. Every portal and checkout method resolves the booking or contract through `checkout.own_booking` or `contract_views.customer_contract`, which answer "not found" for anyone else's record, so ids cannot be probed. Server steps that need ERPNext rights run in `checkout._as_system()`, only after that check. Draft and in-review contracts are never shown to customers. Downloads (invoices, signed contracts) are limited to the booking's own documents.

## Staff

Every desk and staff-app method checks `frappe.has_permission`. The role matrix lives in `services/permissions.py`. Alert rules need write access to Rental Settings.

## HTTP verbs and CSRF

Every whitelisted method names its HTTP verbs. Methods that change data are POST only, so Frappe's CSRF check applies. Fixed in this pass: `booking.cancel`, `deposit.request` and `setup.install_presets` accepted GET.

## Rate limits

Guest endpoints as above. Customer writes (`portal.change`, `portal.cancel`, signing, OTP requests) and downloads are limited per user. Online payments are idempotent per attempt, and a webhook for a paid payment changes nothing.

## Data and secrets

Stripe keys are Password fields (encrypted). No secrets in the repository. SQL uses parameters. The only f-strings in SQL are doctype table names taken from constants. `ignore_permissions=True` is used in 65 places, each with a comment saying why and covered by an ownership test.

## Dependencies

`yarn audit` (runtime): the high advisory in `@vue/server-renderer` is fixed by upgrading `vue` to 3.5.46. Two moderate advisories remain, both inside `frappe-ui` (echarts XSS, postcss-selector-parser CPU use at build time). We render no user supplied echarts options and the parser runs only in the build, so they are accepted until frappe-ui updates. Python: the only runtime dependency is `pyqrcode`, also a Frappe dependency.

## Input fuzzing and PII (T56)

`tests/test_fuzz.py` throws hostile values (SQL and script strings, huge or null input, wrong types, bad dates) at every guest endpoint, against both a missing and a real published item. Findings fixed: blank or unparsable dates and non-text customer details raised bare Python errors; they now give a clear validation message. Dates go through one checked helper (`services/booking.moment`).

Personal data we hold: customer name, email, phone (Customer, Contact, User), signature audit fields (IP, browser) on contracts, payment references. None is written to logs; the event payload carries ids and totals, not contact details. Error logs are written only for failed staff alerts and carry no customer data. Guests never receive another person's data: portal reads are ownership checked and answer "not found" otherwise.

CI now runs a dependency audit (fails on high findings) and a secrets scan in the lint job.
