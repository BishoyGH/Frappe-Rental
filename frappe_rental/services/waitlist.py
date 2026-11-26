"""Waitlist and substitutions (T52).

- A Rental Waitlist Entry asks for an item (or one unit) for a period that is fully booked.
- Whenever units are released (a cancelled booking, a released or expired hold), ``check`` looks at the
  waiting entries for the affected items. Every entry that can now be served is marked Notified and fires
  the ``waitlist_available`` event once, which drives the email Notification and any webhooks (T31).
- ``substitutes`` answers "what else could I offer?" when a request clashes: other free units of the
  same item first, then free items of the same Rental Type.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from frappe_rental.services import availability, events

DOCTYPE = "Rental Waitlist Entry"


def validate(doc) -> None:
	availability.validate_range(doc.from_datetime, doc.to_datetime)
	if flt(doc.qty) <= 0:
		doc.qty = 1
	if doc.rental_unit:
		item = frappe.db.get_value("Rental Unit", doc.rental_unit, "rental_item")
		if item != doc.rental_item:
			frappe.throw(_("Unit {0} does not belong to {1}").format(doc.rental_unit, doc.rental_item))


def add(
	customer: str, rental_item: str, from_datetime, to_datetime, qty: float = 1, rental_unit=None, notes=None
) -> str:
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"customer": customer,
			"rental_item": rental_item,
			"rental_unit": rental_unit,
			"from_datetime": from_datetime,
			"to_datetime": to_datetime,
			"qty": qty or 1,
			"notes": notes,
		}
	)
	doc.insert()
	return doc.name


def can_serve(entry) -> bool:
	rental_type = frappe.db.get_value("Rental Item", entry.rental_item, "rental_type")
	if entry.rental_unit:
		return availability.is_available(
			entry.rental_unit, entry.from_datetime, entry.to_datetime, entry.qty, rental_type
		)
	return bool(
		availability.free_units(
			entry.rental_item, entry.from_datetime, entry.to_datetime, entry.qty, rental_type
		)
	)


def check(rental_items: list[str] | None = None, now=None) -> list[str]:
	"""Notify every waiting entry that can be served now. Idempotent: an entry is notified once."""
	filters = {"status": "Waiting", "to_datetime": [">", now or now_datetime()]}
	if rental_items is not None:
		if not rental_items:
			return []
		filters["rental_item"] = ["in", list(set(rental_items))]
	notified = []
	for name in frappe.get_all(DOCTYPE, filters=filters, pluck="name", order_by="creation asc"):
		entry = frappe.get_doc(DOCTYPE, name)
		if not can_serve(entry):
			continue
		entry.db_set({"status": "Notified", "notified_on": now_datetime()})
		events.emit("waitlist_available", entry)
		notified.append(name)
	return notified


def on_release(booking) -> list[str]:
	"""Called after a booking frees its units."""
	return check([ln.rental_item for ln in booking.lines if ln.rental_item])


def mark_booked(entry_name: str, booking: str) -> None:
	frappe.db.set_value(DOCTYPE, entry_name, {"status": "Booked", "booking": booking})


def expire(now=None) -> int:
	"""Scheduler: entries whose period has started can no longer be served."""
	names = frappe.get_all(
		DOCTYPE,
		filters={"status": ["in", ["Waiting", "Notified"]], "from_datetime": ["<", now or now_datetime()]},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value(DOCTYPE, name, "status", "Cancelled")
	return len(names)


def substitutes(rental_item: str, from_datetime, to_datetime, qty: float = 1, limit: int = 5) -> dict:
	"""Free alternatives for a clashing request: units of the same item, then items of the same type."""
	availability.validate_range(from_datetime, to_datetime)
	start, end = get_datetime(from_datetime), get_datetime(to_datetime)
	rental_type = frappe.db.get_value("Rental Item", rental_item, "rental_type")
	units = availability.free_units(rental_item, start, end, qty, rental_type)[:limit]
	items = []
	if rental_type:
		others = frappe.get_all(
			"Rental Item",
			filters={"rental_type": rental_type, "name": ["!=", rental_item]},
			fields=["name", "item_name"],
			order_by="item_name asc",
		)
		for item in others:
			free = availability.free_units(item.name, start, end, qty, rental_type)
			if free:
				items.append({"rental_item": item.name, "item_name": item.item_name, "rental_unit": free[0]})
			if len(items) >= limit:
				break
	return {"units": units, "items": items}
