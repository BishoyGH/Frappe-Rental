# API

All endpoints are whitelisted methods under `frappe_rental.api.*`, called as
`/api/method/frappe_rental.api.<module>.<method>` with a Frappe API key or session. The full reference, with
parameters and responses, is [`docs/api/openapi.yaml`](../api/openapi.yaml).

- Every method checks permissions; customers only see their own bookings and contracts.
- Create, check-out, check-in and payment calls accept an `Idempotency-Key` header (kept 24 hours); retrying
  with the same key returns the first result.
- Create calls are rate limited (60 per minute per IP).
- Events (booking confirmed, invoice created, contract signed, and so on) are listed in
  [`docs/EVENTS.md`](../EVENTS.md) and can drive Notifications or webhooks.

Groups: availability and pricing, booking lifecycle, payment, contract and signing, maintenance visits,
provider slots and schedule, metering, housekeeping, waitlist, dashboard, setup and import.
