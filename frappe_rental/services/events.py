"""Rental events (T31, D3): named business events, fired once, exposed as hooks, Notifications and Webhooks.

``emit`` writes one Rental Event Log row per (event, document, key). The row's unique ``event_key`` makes every
event fire once, however often the code path runs. Integrations hook in three ways, with no fork:

- Python: apps list handlers under ``rental_event_handlers`` in their ``hooks.py``; each gets ``(event, log)``.
- Frappe Notification on Rental Event Log, event "New", condition ``doc.event == "booking_confirmed"``.
  Default templates for the common events ship disabled (see ``install_notifications``).
- Frappe Webhook on Rental Event Log, doc event ``after_insert``. The payload is documented in docs/EVENTS.md.
"""

import json

import frappe
from frappe.utils import add_to_date, now_datetime

LOG = "Rental Event Log"
EVENTS = (
	"booking_held",
	"booking_confirmed",
	"booking_cancelled",
	"hold_expiring",
	"invoice_created",
	"deposit_requested",
	"deposit_received",
	"handover_done",
	"returned",
	"overdue",
	"waitlist_available",
	"contract_signature_requested",
	"contract_signature_reminder",
	"contract_signed",
	"contract_notice",
	"contract_renewed",
	"contract_ended",
	"damage_reported",
	"sla_breached",
	"housekeeping_overdue",
)


def emit(event: str, doc, key: str | None = None, extra: dict | None = None) -> str | None:
	"""Record ``event`` for ``doc`` once. Returns the log name, or None if it already fired.

	``key`` separates repeatable events (an invoice per period, a reminder per hold); without it an event
	fires once per document.
	"""
	if event not in EVENTS:
		frappe.throw(f"Unknown rental event {event}")
	event_key = f"{event}:{doc.doctype}:{doc.name}" + (f":{key}" if key else "")
	if frappe.db.exists(LOG, {"event_key": event_key}):
		return None
	customer = doc.get("customer")
	log = frappe.get_doc(
		{
			"doctype": LOG,
			"event": event,
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"customer": customer,
			"email": _email(customer),
			"event_key": event_key,
			"payload": json.dumps(payload(event, doc, extra), default=str, indent=1),
		}
	)
	log.flags.ignore_permissions = True  # system record of something the user already did
	try:
		log.insert()
	except frappe.UniqueValidationError:
		return None  # a parallel request fired it first
	from frappe_rental.services import staff_alerts

	staff_alerts.dispatch(log)
	for handler in frappe.get_hooks("rental_event_handlers") or []:
		frappe.get_attr(handler)(event, log)
	return log.name


def payload(event: str, doc, extra: dict | None = None) -> dict:
	"""The documented, stable payload shape (docs/EVENTS.md)."""
	out = {
		"event": event,
		"doctype": doc.doctype,
		"name": doc.name,
		"customer": doc.get("customer"),
		"status": doc.get("status"),
		"at": now_datetime(),
	}
	if doc.doctype == "Rental Booking":
		out.update(
			{
				"from_datetime": doc.from_datetime,
				"to_datetime": doc.to_datetime,
				"rental_type": doc.rental_type,
				"currency": doc.currency,
				"grand_total": doc.grand_total,
				"deposit_required": doc.deposit_required,
				"hold_expires_on": doc.hold_expires_on,
				"items": [
					{"rental_item": ln.rental_item, "rental_unit": ln.rental_unit, "qty": ln.qty}
					for ln in doc.lines
				],
			}
		)
	elif doc.doctype == "Rental Waitlist Entry":
		out.update(
			{
				"rental_item": doc.rental_item,
				"rental_unit": doc.rental_unit,
				"from_datetime": doc.from_datetime,
				"to_datetime": doc.to_datetime,
				"qty": doc.qty,
			}
		)
	elif doc.doctype == "Sales Invoice":
		out.update({"grand_total": doc.grand_total, "currency": doc.currency, "due_date": doc.due_date})
	out.update(extra or {})
	return out


def _email(customer: str | None) -> str | None:
	if not customer:
		return None
	return frappe.db.get_value("Customer", customer, "email_id")


def remind_expiring_holds(now=None, minutes: int = 15) -> int:
	"""Scheduler: fire ``hold_expiring`` once for every hold that expires within ``minutes``."""
	now = now or now_datetime()
	names = frappe.get_all(
		"Rental Booking",
		filters={
			"docstatus": 0,
			"status": "Hold",
			"hold_expires_on": ["between", [now, add_to_date(now, minutes=minutes)]],
		},
		pluck="name",
	)
	fired = 0
	for name in names:
		doc = frappe.get_doc("Rental Booking", name)
		if emit("hold_expiring", doc, key=str(doc.hold_expires_on)):
			fired += 1
	return fired


TEMPLATES = {
	"booking_confirmed": ("Rental: booking confirmed", "Your booking {{ doc.reference_name }} is confirmed."),
	"hold_expiring": (
		"Rental: hold expiring",
		"Your hold {{ doc.reference_name }} expires soon. Confirm it to keep the dates.",
	),
	"overdue": (
		"Rental: return overdue",
		"Booking {{ doc.reference_name }} is overdue. Please return the item.",
	),
	"invoice_created": ("Rental: invoice", "Invoice {{ doc.reference_name }} is ready."),
	"waitlist_available": (
		"Rental: waitlist available",
		"Good news: what you asked for is free again. Contact us to book it before someone else does.",
	),
	"deposit_requested": ("Rental: deposit due", "A deposit is due for booking {{ doc.reference_name }}."),
}


def install_notifications() -> list[str]:
	"""Create the default email Notifications (disabled, so nothing is sent until an admin enables them)."""
	created = []
	for event, (name, message) in TEMPLATES.items():
		if frappe.db.exists("Notification", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification",
				"name": name,
				"subject": name.replace("Rental: ", "").capitalize(),
				"document_type": LOG,
				"event": "New",
				"channel": "Email",
				"enabled": 0,
				"condition": f"doc.event == '{event}'",
				"message": message,
				"recipients": [{"receiver_by_document_field": "email"}],
			}
		).insert(ignore_permissions=True)  # bundled templates installed by setup
		created.append(name)
	return created
