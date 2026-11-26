"""Handover and return (T27): check-out and return of booked units, with stock and asset moves.

A Rental Handover (Check-out or Return) lists the units handed over, a checklist, photos and a
signature. Units are added by scanning any identifier (unit code, barcode, serial, batch, asset).

On submit, per identification mode (D4):
- Asset: an Asset Movement (Transfer) to the "Rented Out" Location; return moves it back.
- Serial or Batch, or a pooled stock item: a Material Transfer from the unit's warehouse to the
  `Rented Out` warehouse (Rental Settings) and back on return. Serial Nos record the booking and
  customer while rented, so each serial's history shows who had it (`serial_history`).
- None: status only.
Unit status: Occupied while out; on return Available, or Maintenance when a line is Damaged or
Missing. Late returns (after the booking end plus the grace period) queue a late fee as a Billable
Event: `late_fee_rate` percent of the booking net total per started day late.
ERPNext calls that differ between versions go through `compat.erpnext`.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import billable_events, events
from frappe_rental.services.unit import find_unit

RENTED_OUT_LOCATION = "Rented Out"


def validate(doc) -> None:
	booking = frappe.get_doc("Rental Booking", doc.rental_booking)
	if booking.docstatus != 1:
		frappe.throw(_("Hand over confirmed bookings only"))
	if doc.scan_input:
		add_scan(doc, doc.scan_input)
		doc.scan_input = None
	booked = {ln.rental_unit for ln in booking.lines}
	for line in doc.lines:
		if line.rental_unit not in booked:
			frappe.throw(
				_("Row {0}: {1} is not on booking {2}").format(line.idx, line.rental_unit, booking.name)
			)
		if flt(line.qty) <= 0:
			line.qty = 1
	if doc.handover_type == "Return":
		_set_late(doc, booking)


def add_scan(doc, code: str) -> str:
	"""Add the unit an identifier points to (once). Returns the unit."""
	unit = find_unit(code.strip())
	if not unit:
		frappe.throw(_("No unit found for {0}").format(code))
	if not any(ln.rental_unit == unit for ln in doc.lines):
		booking_line = frappe.db.get_value(
			"Rental Booking Line", {"parent": doc.rental_booking, "rental_unit": unit}, "qty"
		)
		ids = frappe.db.get_value("Rental Unit", unit, ["serial_no", "batch_no", "asset"], as_dict=True)
		doc.append("lines", {"rental_unit": unit, "qty": flt(booking_line) or 1, **ids})
	return unit


def _set_late(doc, booking) -> None:
	grace = cint(frappe.db.get_single_value("Rental Settings", "grace_period_minutes"))
	due = add_to_date(get_datetime(booking.to_datetime), minutes=grace)
	late = (get_datetime(doc.posted_on) - due).total_seconds() / 60
	doc.is_late = 1 if late > 0 else 0
	doc.late_minutes = math.ceil(late) if late > 0 else 0


def late_fee(booking, late_minutes: int) -> float:
	rate = flt(frappe.db.get_single_value("Rental Settings", "late_fee_rate"))
	if not rate or late_minutes <= 0:
		return 0.0
	days = math.ceil(late_minutes / 1440)
	return flt(flt(booking.net_total) * rate / 100 * days, 2)


def on_submit(doc) -> None:
	booking = frappe.get_doc("Rental Booking", doc.rental_booking)
	out = doc.handover_type == "Check-out"
	if out and booking.status not in ("Confirmed", "Checked Out"):
		frappe.throw(_("Booking {0} is {1}; it cannot be checked out").format(booking.name, booking.status))
	if not out:
		outstanding = units_out(booking.name, exclude=doc.name)
		for line in doc.lines:
			if line.rental_unit not in outstanding:
				frappe.throw(_("Row {0}: {1} was not checked out").format(line.idx, line.rental_unit))
	_move_stock(doc, booking, out)
	_move_assets(doc, booking, out)
	for line in doc.lines:
		_set_unit_status(line, out)
		serial = line.serial_no or frappe.db.get_value("Rental Unit", line.rental_unit, "serial_no")
		if serial:
			frappe.db.set_value(
				"Serial No",
				serial,
				{
					"rental_booking": booking.name if out else None,
					"rental_customer": booking.customer if out else None,
				},
			)
	from frappe_rental.services import metering

	if out:
		booking.db_set("status", "Checked Out")
		metering.from_handover(doc)
		events.emit("handover_done", doc)
		return
	if not units_out(booking.name):
		booking.db_set("status", "Returned")
	fee = late_fee(booking, cint(doc.late_minutes)) if doc.is_late else 0
	if fee:
		billable_events.add(
			booking.name,
			"Late fee",
			fee,
			description=_("Late return: {0} minutes").format(doc.late_minutes),
			source=doc,
		)
	from frappe_rental.services import damage

	damage.from_return(doc)
	metering.from_handover(doc)
	events.emit("returned", doc)


def on_cancel(doc) -> None:
	from frappe_rental.services import metering

	metering.on_handover_cancel(doc)
	if doc.stock_entry and frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus") == 1:
		se = frappe.get_doc("Stock Entry", doc.stock_entry)
		se.flags.ignore_permissions = True  # reverses a permitted handover
		se.cancel()
	for name in (doc.asset_movements or "").split():
		if frappe.db.get_value("Asset Movement", name, "docstatus") == 1:
			am = frappe.get_doc("Asset Movement", name)
			am.flags.ignore_permissions = True
			am.cancel()
	out = doc.handover_type == "Check-out"
	for line in doc.lines:
		_set_unit_status(line, not out, force_available=out)
	booking = frappe.get_doc("Rental Booking", doc.rental_booking)
	booking.db_set("status", "Checked Out" if units_out(booking.name) else "Confirmed")


def units_out(booking: str, exclude: str | None = None) -> set[str]:
	"""Units checked out and not yet returned on submitted handovers (optionally ignoring one)."""
	counts: dict[str, int] = {}
	for row in frappe.db.sql(
		"""select l.rental_unit, h.handover_type from `tabRental Handover Line` l
		join `tabRental Handover` h on h.name = l.parent
		where h.rental_booking = %s and h.docstatus = 1 and h.name != %s""",
		(booking, exclude or ""),
		as_dict=True,
	):
		counts[row.rental_unit] = counts.get(row.rental_unit, 0) + (
			1 if row.handover_type == "Check-out" else -1
		)
	return {u for u, n in counts.items() if n > 0}


def _set_unit_status(line, out: bool, force_available: bool = False) -> None:
	if frappe.db.get_value("Rental Unit", line.rental_unit, "identification_mode") == "Pooled":
		return  # pooled units stay Available; availability counts quantities
	if out:
		status = "Occupied"
	elif force_available or line.condition == "Good":
		status = "Available"
	else:
		status = "Maintenance"
	frappe.db.set_value("Rental Unit", line.rental_unit, "status", status)


def _move_stock(doc, booking, out: bool) -> None:
	rented_out = frappe.db.get_single_value("Rental Settings", "rented_out_warehouse")
	rows = []
	for line in doc.lines:
		unit = frappe.db.get_value(
			"Rental Unit",
			line.rental_unit,
			["warehouse", "rental_item", "serial_no", "batch_no"],
			as_dict=True,
		)
		item_code = frappe.db.get_value("Rental Item", unit.rental_item, "item_code")
		if not item_code or not frappe.db.get_value("Item", item_code, "is_stock_item") or not unit.warehouse:
			continue
		if not rented_out:
			frappe.throw(_("Set the Rented Out warehouse in Rental Settings"))
		src, dst = (unit.warehouse, rented_out) if out else (rented_out, unit.warehouse)
		row = {"item_code": item_code, "qty": flt(line.qty) or 1, "s_warehouse": src, "t_warehouse": dst}
		if line.serial_no or unit.serial_no:
			row["serial_no"] = line.serial_no or unit.serial_no
			row["qty"] = len(row["serial_no"].split())
		if line.batch_no or unit.batch_no:
			row["batch_no"] = line.batch_no or unit.batch_no
		if booking.cost_center:
			row["cost_center"] = booking.cost_center
		rows.append(row)
	if rows:
		name = compat.stock_transfer(booking.company, rows, {"rental_handover": doc.name})
		doc.db_set("stock_entry", name)


def _move_assets(doc, booking, out: bool) -> None:
	moved = []
	for line in doc.lines:
		asset = line.asset or frappe.db.get_value("Rental Unit", line.rental_unit, "asset")
		if not asset:
			continue
		target = _rented_out_location() if out else _home_location(booking.name, asset)
		if not target or frappe.db.get_value("Asset", asset, "location") == target:
			continue
		moved.append(compat.move_asset(asset, booking.company, target, {"rental_handover": doc.name}))
	if moved:
		doc.db_set("asset_movements", "\n".join(moved))


def _rented_out_location() -> str:
	if not frappe.db.exists("Location", RENTED_OUT_LOCATION):
		frappe.get_doc({"doctype": "Location", "location_name": RENTED_OUT_LOCATION}).insert(
			ignore_permissions=True  # system location for rented assets
		)
	return RENTED_OUT_LOCATION


def _home_location(booking: str, asset: str) -> str | None:
	"""Where the asset was before this booking's check-out."""
	row = frappe.db.sql(
		"""select i.source_location from `tabAsset Movement Item` i
		join `tabAsset Movement` m on m.name = i.parent
		join `tabRental Handover` h on h.name = m.rental_handover
		where h.rental_booking = %s and h.handover_type = 'Check-out' and m.docstatus = 1 and i.asset = %s
		order by m.creation desc limit 1""",
		(booking, asset),
	)
	return row[0][0] if row else None


def check_overdue(now=None) -> int:
	"""Scheduler: fire `overdue` once a day for each booking still out after its end plus grace."""
	now = get_datetime(now or now_datetime())
	grace = cint(frappe.db.get_single_value("Rental Settings", "grace_period_minutes"))
	names = frappe.get_all(
		"Rental Booking",
		filters={
			"docstatus": 1,
			"status": "Checked Out",
			"to_datetime": ["<", add_to_date(now, minutes=-grace)],
		},
		pluck="name",
	)
	fired = 0
	for name in names:
		if events.emit("overdue", frappe.get_doc("Rental Booking", name), key=str(now.date())):
			fired += 1
	return fired


def serial_history(serial_no: str) -> list[dict]:
	"""Every handover of a serial: when, which booking, which customer, out or back."""
	return frappe.db.sql(
		"""select h.posted_on, h.handover_type, h.rental_booking, h.customer, h.name as handover
		from `tabRental Handover Line` l join `tabRental Handover` h on h.name = l.parent
		where l.serial_no = %s and h.docstatus = 1 order by h.posted_on""",
		serial_no,
		as_dict=True,
	)
