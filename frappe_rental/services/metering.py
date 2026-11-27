"""Metered usage (T49): meter readings, allowance and overage billing.

- Readings are Rental Meter Reading rows per booking and unit. Handovers record them from each line's
  `meter_reading` (source Check-out or Return); staff or devices add Interim/API readings.
- Usage per unit = latest reading minus the first one. Readings may not go backwards.
- Allowance and rate: a contract booking uses the contract's `included_allowance` and `overage_rate`
  (CONTRACTS usage terms); otherwise the Rental Type's `included_allowance` (per booking) and
  `overage_rate`. Allowance is per booking.
- When the last unit comes back, `settle` queues usage above the allowance as one Overage Billable
  Event (once per booking). Cancelling a return removes its readings and a not-yet-invoiced Overage.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from frappe_rental.services import billable_events

DOCTYPE = "Rental Meter Reading"


def validate_reading(doc) -> None:
	if flt(doc.reading) < 0:
		frappe.throw(_("A reading cannot be negative"))
	if frappe.db.get_value("Rental Booking", doc.rental_booking, "docstatus") != 1:
		frappe.throw(_("Readings are taken on submitted bookings only"))
	units = {
		r.rental_unit
		for r in frappe.get_all(
			"Rental Booking Line", filters={"parent": doc.rental_booking}, fields=["rental_unit"]
		)
	}
	if doc.rental_unit not in units:
		frappe.throw(_("{0} is not on booking {1}").format(doc.rental_unit, doc.rental_booking))
	doc.meter_unit = _terms(doc.rental_booking)["meter_unit"]
	last = frappe.get_all(
		DOCTYPE,
		filters={
			"rental_booking": doc.rental_booking,
			"rental_unit": doc.rental_unit,
			"name": ["!=", doc.name or ""],
			"read_on": ["<=", doc.read_on],
		},
		fields=["reading"],
		order_by="read_on desc",
		limit=1,
	)
	if last and flt(doc.reading) < flt(last[0].reading):
		frappe.throw(_("The meter cannot go back from {0} to {1}").format(last[0].reading, doc.reading))


def record(booking: str, unit: str, reading, source: str = "API", read_on=None, handover=None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"rental_booking": booking,
			"rental_unit": unit,
			"reading": flt(reading),
			"read_on": read_on or now_datetime(),
			"source": source,
			"rental_handover": handover,
		}
	)
	doc.flags.ignore_permissions = bool(handover)  # handover submit was permission-checked
	doc.insert()
	return doc.name


def _terms(booking: str) -> dict:
	b = frappe.db.get_value("Rental Booking", booking, ["rental_type", "rental_contract"], as_dict=True)
	rtype = (
		frappe.db.get_value(
			"Rental Type", b.rental_type, ["meter_unit", "included_allowance", "overage_rate"], as_dict=True
		)
		or frappe._dict()
	)
	out = {
		"meter_unit": rtype.meter_unit,
		"allowance": flt(rtype.included_allowance),
		"rate": flt(rtype.overage_rate),
	}
	if b.rental_contract:
		c = frappe.db.get_value(
			"Rental Contract",
			b.rental_contract,
			["included_allowance", "allowance_unit", "overage_rate"],
			as_dict=True,
		)
		if c and (flt(c.included_allowance) or flt(c.overage_rate)):
			out = {
				"meter_unit": c.allowance_unit or out["meter_unit"],
				"allowance": flt(c.included_allowance),
				"rate": flt(c.overage_rate),
			}
	return out


def usage(booking: str) -> dict:
	"""{unit: used} and the total, from first and latest reading per unit."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"rental_booking": booking},
		fields=["rental_unit", "reading"],
		order_by="read_on asc, creation asc",
	)
	first, last = {}, {}
	for r in rows:
		first.setdefault(r.rental_unit, flt(r.reading))
		last[r.rental_unit] = flt(r.reading)
	per_unit = {u: flt(last[u] - first[u], 3) for u in first}
	return {"units": per_unit, "total": flt(sum(per_unit.values()), 3)}


def summary(booking: str) -> dict:
	terms = _terms(booking)
	used = usage(booking)
	over = max(0.0, used["total"] - terms["allowance"])
	return {**terms, **used, "overage": flt(over, 3), "amount": flt(over * terms["rate"], 2)}


def settle(booking: str) -> str | None:
	"""Queue the overage as one Billable Event; safe to run twice."""
	s = summary(booking)
	if s["amount"] <= 0:
		return None
	doc = frappe.get_doc("Rental Booking", booking)
	return billable_events.add(
		booking,
		"Overage",
		s["amount"],
		description=_("{0} {1} above the {2} included").format(
			s["overage"], s["meter_unit"] or "", s["allowance"]
		),
		source=doc,
	)


def from_handover(doc) -> None:
	"""Handover submit: record line readings; settle once everything is back."""
	source = "Check-out" if doc.handover_type == "Check-out" else "Return"
	for line in doc.lines:
		if line.rental_unit and flt(line.meter_reading):
			record(doc.rental_booking, line.rental_unit, line.meter_reading, source, doc.posted_on, doc.name)
	if (
		source == "Return"
		and frappe.db.get_value("Rental Booking", doc.rental_booking, "status") == "Returned"
	):
		settle(doc.rental_booking)


def on_handover_cancel(doc) -> None:
	for name in frappe.get_all(DOCTYPE, filters={"rental_handover": doc.name}, pluck="name"):
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)  # part of the permitted cancel
	if doc.handover_type == "Return":
		for name in frappe.get_all(
			"Rental Billable Event",
			filters={"rental_booking": doc.rental_booking, "event_type": "Overage", "status": "Pending"},
			pluck="name",
		):
			frappe.delete_doc("Rental Billable Event", name, ignore_permissions=True)
