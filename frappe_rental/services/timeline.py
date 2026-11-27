"""Resource timeline for the staff calendar (T19): units as rows, bookings and blocks as bars, and moving a booking.

Reads are bulk (one query each for units, booking lines and blocks) and go through permission-aware ``get_list``
for the parent documents. Moves reuse the availability rules, so a conflicting drop is rejected by the server.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime

from frappe_rental.services import availability
from frappe_rental.services.search import _candidate_units

MAX_DAYS = 62
MOVABLE = ("Draft", "Hold")


def timeline(start, end, location: str | None = None, rental_type: str | None = None) -> dict:
	"""Units (rows) with their bookings and blocks between ``start`` and ``end``."""
	start, end = get_datetime(start), get_datetime(end)
	availability.validate_range(start, end)
	if end - start > timedelta(days=MAX_DAYS):
		frappe.throw(_("Show at most {0} days at once").format(MAX_DAYS))
	units = _candidate_units(rental_type, None, location, None)
	units.sort(key=lambda u: (u.location or "", u.item_name or "", u.unit_name or u.name))
	names = [u.name for u in units]
	events = {n: [] for n in names}
	if names:
		for e in _booking_events(names, start, end) + _block_events(names, start, end):
			events[e.pop("rental_unit")].append(e)
	return {
		"start": start,
		"end": end,
		"units": [
			{
				"name": u.name,
				"unit_name": u.unit_name,
				"item_name": u.item_name,
				"rental_item": u.rental_item,
				"rental_type": u.rental_type,
				"location": u.location,
				"events": sorted(events[u.name], key=lambda e: get_datetime(e["start"])),
			}
			for u in units
		],
	}


def _booking_events(units: list[str], start, end) -> list[dict]:
	line = frappe.qb.DocType("Rental Booking Line")
	booking = frappe.qb.DocType("Rental Booking")
	rows = (
		frappe.qb.from_(line)
		.join(booking)
		.on(booking.name == line.parent)
		.select(
			line.rental_unit,
			line.parent,
			line.from_datetime.as_("line_from"),
			line.to_datetime.as_("line_to"),
			booking.from_datetime,
			booking.to_datetime,
		)
		.where(line.parenttype == "Rental Booking")
		.where(line.rental_unit.isin(units))
		.where(booking.docstatus < 2)
		.where(booking.status.notin(("Cancelled", "No Show")))
		.where(booking.from_datetime < end)
		.where(booking.to_datetime > start)
		.run(as_dict=True)
	)
	if not rows:
		return []
	# Only bookings the user may read; the raw join above is narrowed to them here.
	readable = {
		b.name: b
		for b in frappe.get_list(
			"Rental Booking",
			filters={"name": ["in", list({r.parent for r in rows})]},
			fields=["name", "customer", "status", "docstatus"],
			limit_page_length=0,
		)
	}
	customers = dict(
		frappe.get_all(
			"Customer",
			filters={"name": ["in", list({b.customer for b in readable.values()})]},
			fields=["name", "customer_name"],
			as_list=True,
		)
	)
	out = []
	for r in rows:
		b = readable.get(r.parent)
		if not b:
			continue
		out.append(
			{
				"rental_unit": r.rental_unit,
				"kind": "booking",
				"name": b.name,
				"label": customers.get(b.customer, b.customer),
				"status": b.status,
				"movable": b.status in MOVABLE and b.docstatus == 0,
				"start": r.line_from or r.from_datetime,
				"end": r.line_to or r.to_datetime,
			}
		)
	return out


def _block_events(units: list[str], start, end) -> list[dict]:
	blocks = frappe.get_list(
		"Rental Block",
		filters=[
			["rental_unit", "in", units],
			["from_datetime", "<", end],
		],
		or_filters=[["to_datetime", "is", "not set"], ["to_datetime", ">", start]],
		fields=["name", "rental_unit", "reason", "from_datetime", "to_datetime"],
		limit_page_length=0,
	)
	return [
		{
			"rental_unit": b.rental_unit,
			"kind": "block",
			"name": b.name,
			"label": _(b.reason) if b.reason else _("Blocked"),
			"status": "Blocked",
			"movable": False,
			"start": b.from_datetime,
			"end": b.to_datetime or end,
		}
		for b in blocks
	]


def move_booking(doc, from_datetime, to_datetime, rental_unit: str | None = None) -> None:
	"""Move a draft or held booking to new dates and, for a one-line booking, to another unit.

	Confirmed bookings are not moved here: changing a submitted booking goes through amendment.
	Raises ``UnavailableError`` when the target is taken; nothing is saved then.
	"""
	if doc.docstatus != 0 or doc.status not in MOVABLE:
		frappe.throw(_("Only draft or held bookings can be moved"))
	start, end = get_datetime(from_datetime), get_datetime(to_datetime)
	availability.validate_range(start, end)
	if rental_unit and len(doc.lines) != 1:
		frappe.throw(_("Only a booking with one item can be moved to another unit"))
	if (
		rental_unit
		and frappe.db.get_value("Rental Unit", rental_unit, "rental_item") != doc.lines[0].rental_item
	):
		frappe.throw(_("Unit {0} is not of the booked item").format(rental_unit))
	doc.from_datetime, doc.to_datetime = start, end
	for line in doc.lines:
		line.from_datetime = line.to_datetime = None
		if rental_unit:
			line.rental_unit = rental_unit
	if doc.status != "Hold":
		# A draft holds nothing in the cache, so check the target explicitly (a hold re-reserves on save).
		source = ("Rental Booking", doc.name)
		for line in doc.lines:
			if line.rental_unit and not availability.is_available(
				line.rental_unit, start, end, line.qty, doc.rental_type, source
			):
				raise availability.UnavailableError(
					_("Unit {0} is not available for that period").format(line.rental_unit)
				)
	frappe.db.savepoint("rental_move")
	try:
		doc.save()  # a held booking re-reserves in on_update and raises on a clash
	except Exception:
		frappe.db.rollback(save_point="rental_move")
		raise
