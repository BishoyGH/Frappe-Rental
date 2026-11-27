"""Maintenance visits (T46, PLAN maintenance contract, CONTRACTS behaviour 7).

- `generate(contract)` plans one visit per `visit_frequency` period over the contract term (12 months
  ahead when open-ended), on the term's anniversary dates. It only adds dates not planned yet, so it
  is safe to run twice; activation runs it.
- `assign(contract, visit, technician, start)` books the technician (a Provider unit, so working hours
  apply) as a Rental Booking under the contract, and marks the visit Booked. Re-assigning cancels the
  previous booking.
- `request_service(contract, notes)` adds an unplanned visit with SLA deadlines from the contract:
  response due (`sla_response_hours`, met by assigning) and resolution due (`sla_resolution_hours`,
  met by completing).
- `complete(contract, visit, notes)` marks it Done and flags a late finish as an SLA breach.
- `check_sla(now)` (hourly) flags open visits whose deadline passed, and planned visits more than a
  day past their date as Missed.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_datetime, getdate, now_datetime

from frappe_rental.services import events

STEP_MONTHS = {"Monthly": 1, "Quarterly": 3, "Semi-annual": 6, "Yearly": 12}
OPEN = ("Planned", "Booked")
RUNNING = ("Active", "Suspended", "Ending")


def _row(contract, name):
	for row in contract.get("visits") or []:
		if row.name == name:
			return row
	frappe.throw(_("Visit {0} not found").format(name))


def plan_dates(start, end, frequency) -> list:
	step = STEP_MONTHS.get(frequency or "")
	if not step:
		return []
	start, end = getdate(start), getdate(end)
	out, k = [], 0
	while True:
		d = getdate(add_months(start, step * k))
		if d > end:
			return out
		out.append(d)
		k += 1


def generate(contract, save: bool = True) -> int:
	"""Add Planned visits for missing dates. Returns how many were added."""
	if not contract.get("visit_frequency"):
		return 0
	end = contract.end_date if not contract.open_ended else add_months(contract.start_date, 12)
	if not end:
		return 0
	have = {getdate(r.planned_date) for r in contract.get("visits") or [] if r.visit_type == "Scheduled"}
	added = 0
	for d in plan_dates(contract.start_date, end, contract.visit_frequency):
		if d not in have:
			contract.append("visits", {"planned_date": d, "visit_type": "Scheduled", "status": "Planned"})
			added += 1
	if added and save:
		contract.save()
	return added


def _running(contract):
	if contract.status not in RUNNING:
		frappe.throw(_("Contract {0} is not running").format(contract.name))


def assign(contract, visit: str, technician: str, start, hours: float = 2) -> str:
	"""Book the technician for the visit; returns the booking name."""
	_running(contract)
	row = _row(contract, visit)
	if row.status not in OPEN:
		frappe.throw(_("Visit {0} is {1}").format(visit, _(row.status)))
	if frappe.db.get_value("Rental Unit", technician, "unit_type") != "Provider":
		frappe.throw(_("{0} is not a provider").format(technician))
	start = get_datetime(start)
	end = start + timedelta(hours=flt(hours) or 2)
	item = frappe.db.get_value("Rental Unit", technician, "rental_item")
	booking = frappe.get_doc(
		{
			"doctype": "Rental Booking",
			"customer": contract.customer,
			"company": contract.company,
			"rental_type": frappe.db.get_value("Rental Item", item, "rental_type"),
			"rental_contract": contract.name,
			"from_datetime": start,
			"to_datetime": end,
			"lines": [{"rental_item": item, "rental_unit": technician, "qty": 1}],
		}
	).insert()
	booking.submit()
	previous = row.rental_booking
	row.update({"technician": technician, "rental_booking": booking.name, "status": "Booked"})
	if row.response_due and now_datetime() > get_datetime(row.response_due):
		row.sla_breached = 1
	contract.save()
	if row.sla_breached:
		events.emit("sla_breached", contract, key=row.name)
	if previous and frappe.db.get_value("Rental Booking", previous, "docstatus") == 1:
		frappe.get_doc("Rental Booking", previous).cancel()
	return booking.name


def request_service(contract, notes: str, now=None) -> str:
	_running(contract)
	if not notes:
		frappe.throw(_("Describe the problem"))
	now = get_datetime(now or now_datetime())

	def due(h):
		return now + timedelta(hours=flt(h)) if flt(h) else None

	row = contract.append(
		"visits",
		{
			"planned_date": getdate(now),
			"visit_type": "Service request",
			"status": "Planned",
			"requested_on": now,
			"response_due": due(contract.sla_response_hours),
			"resolution_due": due(contract.sla_resolution_hours),
			"notes": notes,
		},
	)
	contract.save()
	return row.name


def complete(contract, visit: str, notes: str | None = None, on=None) -> None:
	row = _row(contract, visit)
	if row.status not in OPEN:
		frappe.throw(_("Visit {0} is {1}").format(visit, _(row.status)))
	done = get_datetime(on or now_datetime())
	row.status, row.completed_on = "Done", done
	if notes:
		row.notes = notes
	if row.resolution_due and done > get_datetime(row.resolution_due):
		row.sla_breached = 1
	contract.save()
	if row.sla_breached:
		events.emit("sla_breached", contract, key=row.name)


def check_sla(now=None) -> int:
	"""Scheduler (hourly): flag breaches and missed visits. Returns rows changed; safe to rerun."""
	now = get_datetime(now or now_datetime())
	rows = frappe.get_all(
		"Rental Contract Visit",
		filters={"parenttype": "Rental Contract", "status": ["in", OPEN]},
		fields=[
			"name",
			"parent",
			"status",
			"planned_date",
			"response_due",
			"resolution_due",
			"sla_breached",
			"visit_type",
		],
	)
	changed = 0
	for r in rows:
		late = (r.status == "Planned" and r.response_due and get_datetime(r.response_due) < now) or (
			r.resolution_due and get_datetime(r.resolution_due) < now
		)
		missed = (
			r.visit_type == "Scheduled"
			and r.status == "Planned"
			and getdate(r.planned_date) < getdate(now - timedelta(days=1))
		)
		values = {}
		if late and not r.sla_breached:
			values["sla_breached"] = 1
		if missed:
			values["status"] = "Missed"
		if values:
			frappe.db.set_value("Rental Contract Visit", r.name, values, update_modified=False)
			changed += 1
			if values.get("sla_breached"):
				events.emit("sla_breached", frappe.get_doc("Rental Contract", r.parent), key=r.name)
	return changed
