# Rental events (T31)

Business events are recorded as **Rental Event Log** rows. The unique `event_key` makes each event fire once.

| Event | Fired when | Reference |
|---|---|---|
| `booking_held` | a draft is held (once per hold) | Rental Booking |
| `booking_confirmed` | a booking is submitted | Rental Booking |
| `booking_cancelled` | a hold is released or a confirmed booking cancelled | Rental Booking |
| `hold_expiring` | a hold expires within 15 minutes (scheduler, every 5 min) | Rental Booking |
| `invoice_created` | the booking's Sales Invoice is submitted | Sales Invoice |
| `deposit_requested`, `deposit_received` | deposits (T25) | Rental Deposit |
| `handover_done`, `returned` | handover and return (T27) | Rental Handover |
| `overdue` | hourly overdue check (T27) | Rental Booking |
| `waitlist_available` | units freed by a cancel or an expired hold (T52) | Rental Waitlist Entry |
| `contract_signature_requested`, `contract_signature_reminder`, `contract_signed` | e-signature (T41); the reminder fires every 3 days while unsigned | Rental Contract |

## Hooking in

You have three options:

- **Python:** add `rental_event_handlers = ["my_app.module.handler"]` to your app's `hooks.py`. Each handler is called as `handler(event, log)`.
- **Notifications:** six email templates ship **disabled**: confirmed, hold expiring, overdue, invoice, deposit due and waitlist available. Enable them in Notification. Each one is a Notification on Rental Event Log, with event `New` and condition `doc.event == "<event>"`. It goes to the customer's email.
- **Webhooks:** create a Frappe Webhook on `Rental Event Log` with doc event `after_insert`. The request body can use `doc.payload`, which is the JSON below.

## Payload

The payload is stable and new keys are only ever added.

```json
{
  "event": "booking_confirmed",
  "doctype": "Rental Booking",
  "name": "RB-2026-00012",
  "customer": "Sara Mahmoud",
  "status": "Confirmed",
  "at": "2026-11-26 15:40:00",
  "from_datetime": "2026-12-01 14:00:00",
  "to_datetime": "2026-12-31 12:00:00",
  "rental_type": "Apartment",
  "currency": "EGP",
  "grand_total": 20520.0,
  "deposit_required": 16000.0,
  "hold_expires_on": null,
  "items": [{"rental_item": "RI-00001", "rental_unit": "RU-00004", "qty": 1}]
}
```

For `invoice_created`, the payload carries `grand_total`, `currency`, `due_date` and `rental_booking`.

For `waitlist_available`, the payload carries `rental_item`, `rental_unit`, `from_datetime`, `to_datetime` and `qty` of the waitlist entry.
