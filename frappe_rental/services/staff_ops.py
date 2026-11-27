"""Views and edits behind the staff app's operations screens (T29).

- ``handover_state``: what the Handovers screen needs for one booking: each booked unit, whether it is out,
  the next step (Check-out or Return) and the handovers so far.
- ``find_booking``: scan-first entry. A scanned code (booking name, barcode, serial or external ID) resolves
  to the booking that has that unit now, or next.
- ``billing``: the booking's schedule rows with invoice status; ``save_schedule`` edits planned rows.
- ``panels``: deposit and damage reports for the booking tabs.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, now_datetime

from frappe_rental.services import handover
from frappe_rental.services.billing import LOCKED
from frappe_rental.services.unit import find_unit

OPEN = ("Confirmed", "Checked Out")


def handover_state(booking) -> dict:
	out = handover.units_out(booking.name)
	units = {ln.rental_unit for ln in booking.lines if ln.rental_unit}
	info = {
		u.name: u
		for u in frappe.get_all(
			"Rental Unit",
			filters={"name": ["in", list(units) or [""]]},
			fields=["name", "unit_name", "barcode", "serial_no", "rental_item"],
		)
	}
	lines = []
	for ln in booking.lines:
		u = info.get(ln.rental_unit) or frappe._dict()
		lines.append(
			{
				"rental_unit": ln.rental_unit,
				"unit_name": u.get("unit_name") or ln.rental_unit,
				"rental_item": ln.rental_item,
				"barcode": u.get("barcode"),
				"serial_no": u.get("serial_no"),
				"qty": ln.qty,
				"out": ln.rental_unit in out,
			}
		)
	if booking.docstatus != 1 or booking.status not in OPEN:
		next_step = None
	else:
		next_step = "Return" if out else "Check-out"
	history = frappe.get_all(
		"Rental Handover",
		filters={"rental_booking": booking.name, "docstatus": 1},
		fields=["name", "handover_type", "posted_on", "is_late", "late_minutes"],
		order_by="posted_on asc",
	)
	return {
		"name": booking.name,
		"customer": booking.customer,
		"customer_name": frappe.db.get_value("Customer", booking.customer, "customer_name")
		or booking.customer,
		"status": booking.status,
		"from_datetime": booking.from_datetime,
		"to_datetime": booking.to_datetime,
		"lines": lines,
		"next_step": next_step,
		"history": history,
	}


def find_booking(code: str) -> str | None:
	code = (code or "").strip()
	if not code:
		return None
	if frappe.db.exists("Rental Booking", code):
		return code
	unit = find_unit(code)
	if not unit:
		return None
	rows = frappe.db.sql(
		"""select b.name, b.status, b.from_datetime from `tabRental Booking` b
		join `tabRental Booking Line` l on l.parent = b.name
		where l.rental_unit = %s and b.docstatus = 1 and b.status in ('Confirmed', 'Checked Out')""",
		unit,
		as_dict=True,
	)
	if not rows:
		return None
	# Checked-out bookings first, then the one starting closest to now. Sorted here, not in SQL,
	# because date-difference functions differ between MariaDB and Postgres.
	now = now_datetime()
	rows.sort(
		key=lambda r: (r.status != "Checked Out", abs((get_datetime(r.from_datetime) - now).total_seconds()))
	)
	return rows[0].name


def billing(booking) -> dict:
	rows = [
		{
			"idx": r.idx,
			"period_from": r.period_from,
			"period_to": r.period_to,
			"invoice_date": r.invoice_date,
			"amount": r.amount,
			"status": r.status,
			"sales_invoice": r.sales_invoice,
			"adjustment_note": r.adjustment_note,
			"editable": r.status not in LOCKED,
		}
		for r in booking.get("billing_schedule") or []
	]
	plan = (booking.get("billing_plan") or [None])[0]
	return {
		"currency": booking.currency,
		"net_total": booking.net_total,
		"plan": plan.as_dict() if plan else None,
		"rows": rows,
		"invoiced": sum(flt(r["amount"]) for r in rows if not r["editable"]),
		"planned": sum(flt(r["amount"]) for r in rows if r["editable"]),
	}


def save_schedule(booking, rows: list[dict]) -> dict:
	"""Edit invoice dates, amounts and notes of planned rows. The schedule total must stay the net total."""
	by_idx = {r.idx: r for r in booking.get("billing_schedule") or []}
	for data in rows:
		row = by_idx.get(int(data.get("idx") or 0))
		if not row:
			frappe.throw(_("Schedule row {0} not found").format(data.get("idx")))
		changes = {k: data[k] for k in ("invoice_date", "amount", "adjustment_note") if k in data}
		if row.status in LOCKED:
			if any(str(row.get(k) or "") != str(v or "") for k, v in changes.items()):
				frappe.throw(_("Row {0} is {1} and cannot change").format(row.idx, _(row.status)))
			continue
		if "amount" in changes and flt(changes["amount"]) < 0:
			frappe.throw(_("Row {0}: the amount cannot be negative").format(row.idx))
		if "invoice_date" in changes:
			changes["invoice_date"] = getdate(changes["invoice_date"])
		row.update(changes)
	precision = frappe.get_precision("Rental Billing Schedule", "amount") or 2
	total = round(sum(flt(r.amount) for r in booking.billing_schedule), precision)
	if abs(total - round(flt(booking.net_total), precision)) > 10 ** (-precision) / 2:
		frappe.throw(
			_("The schedule adds up to {0}; it must equal the net total {1}").format(total, booking.net_total)
		)
	if booking.docstatus == 1:
		booking.flags.ignore_validate_update_after_submit = False
		booking.save()  # schedule fields are allow-on-submit
	else:
		booking.save()
	return billing(booking)


def panels(booking) -> dict:
	deposit = frappe.db.get_value("Rental Deposit", {"rental_booking": booking.name})
	dep = None
	if deposit:
		d = frappe.get_doc("Rental Deposit", deposit)
		dep = {
			"name": d.name,
			"status": d.status,
			"currency": d.currency,
			"amount_required": d.amount_required,
			"amount_received": d.amount_received,
			"amount_applied": d.amount_applied,
			"amount_refunded": d.amount_refunded,
			"amount_forfeited": d.amount_forfeited,
			"balance_held": d.balance_held,
			"entries": [
				{k: e.get(k) for k in ("action", "amount", "posting_date", "journal_entry", "remarks")}
				for e in d.entries
			],
		}
	damages = frappe.get_all(
		"Rental Damage Report",
		filters={"rental_booking": booking.name},
		fields=[
			"name",
			"rental_unit",
			"description",
			"status",
			"estimate_amount",
			"approved_amount",
			"settlement",
			"reported_on",
		],
		order_by="creation asc",
	)
	return {"deposit": dep, "damages": damages}
