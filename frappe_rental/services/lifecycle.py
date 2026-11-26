"""Booking lifecycle (T14): Draft -> Hold -> Confirmed, plus cancel and hold expiry.

- A hold is a saved draft with status Hold. It writes availability rows and expires after
  `Rental Settings.hold_expiry_minutes`; the scheduler returns expired holds to Draft and frees units.
- Confirming is submitting. Guards run in `before_submit`: hold first (if the type requires it),
  deposit paid (if required), a signed contract (if required) and availability, which also assigns units.
- Cancelling a confirmed booking (docstatus 2) or a held draft frees its units.
Every step is idempotent: reserving replaces the booking's previous rows, releasing twice is a no-op.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, get_datetime, now_datetime

from frappe_rental.services import availability, cancellation, deposits, erpnext_sync, events, invoicing

SOURCE = "Rental Booking"


def hold_minutes() -> int:
	return int(frappe.db.get_single_value("Rental Settings", "hold_expiry_minutes") or 15)


def place_hold(doc) -> None:
	"""Draft -> Hold: reserve the units and start the expiry clock."""
	if doc.docstatus != 0 or doc.status not in ("Draft", "Hold"):
		frappe.throw(_("Only a draft booking can be held"))
	doc.status = "Hold"
	doc.hold_expires_on = add_to_date(now_datetime(), minutes=hold_minutes())
	doc.save()  # on_update reserves
	events.emit("booking_held", doc, key=str(doc.hold_expires_on))
	deposits.request(doc)


def on_update(doc) -> None:
	"""A held draft re-reserves on every save, so edits to dates or lines are checked."""
	if doc.docstatus == 0 and doc.status == "Hold":
		availability.reserve_booking(doc)


def before_submit(doc) -> None:
	rtype = frappe.get_cached_doc("Rental Type", doc.rental_type)
	if rtype.requires_hold and doc.status != "Hold":
		frappe.throw(_("{0} bookings must be held before they are confirmed").format(doc.rental_type))
	if doc.status == "Hold" and doc.hold_expires_on and get_datetime(doc.hold_expires_on) < now_datetime():
		frappe.throw(_("The hold expired; place a new hold"))
	if rtype.requires_deposit and flt(doc.deposit_paid) < flt(doc.deposit_required):
		frappe.throw(
			_("A deposit of {0} is required before confirming; {1} is paid").format(
				doc.deposit_required, flt(doc.deposit_paid)
			)
		)
	if rtype.requires_contract:
		if not doc.contract:
			frappe.throw(_("{0} bookings need a contract before they are confirmed").format(doc.rental_type))
		if not frappe.db.get_value("Contract", doc.contract, "is_signed"):
			frappe.throw(_("Contract {0} is not signed").format(doc.contract))
	availability.reserve_booking(doc)
	doc.status = "Confirmed"
	doc.hold_expires_on = None


def on_submit(doc) -> None:
	"""Mirror the confirmed booking in ERPNext; invoice now when Rental Settings auto-invoices."""
	erpnext_sync.make_sales_order(doc)
	events.emit("booking_confirmed", doc)
	deposits.request(doc)
	invoicing.on_confirm(doc)


def on_cancel(doc) -> None:
	availability.release(SOURCE, doc.name)
	if doc.flags.get("cancellation"):
		cancellation.settle(doc, doc.flags.cancellation)
	else:
		erpnext_sync.reverse(doc)
	doc.db_set("status", "Cancelled")
	events.emit("booking_cancelled", doc)


def on_trash(doc) -> None:
	availability.release(SOURCE, doc.name)


def cancel(doc) -> None:
	"""Cancel a confirmed booking, or release a held draft."""
	if doc.docstatus == 1:
		doc.cancel()
	elif doc.docstatus == 0 and doc.status == "Hold":
		availability.release(SOURCE, doc.name)
		doc.db_set({"status": "Cancelled", "hold_expires_on": None})
		events.emit("booking_cancelled", doc)
	else:
		frappe.throw(_("Only a held or confirmed booking can be cancelled"))


def expire_holds(now=None) -> list[str]:
	"""Scheduler job: return expired holds to Draft and free their units. Safe to run twice."""
	names = frappe.get_all(
		SOURCE,
		filters={"docstatus": 0, "status": "Hold", "hold_expires_on": ["<", now or now_datetime()]},
		pluck="name",
	)
	for name in names:
		availability.release(SOURCE, name)
		frappe.db.set_value(SOURCE, name, {"status": "Draft", "hold_expires_on": None})
		frappe.get_doc(SOURCE, name).add_comment("Info", _("Hold expired; units released"))
	return names
