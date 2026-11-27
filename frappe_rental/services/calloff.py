"""Call-off bookings and entitlements (T43, D7 behaviour 2 and 7).

A booking with `rental_contract` and `contract_allocation` draws on that allocation row:
- the contract must be Active, for the same customer, and the booking inside the row's period;
- Specific unit / Quantity rows: the line uses the allocated unit, and the contract's own cache rows
  for it do not count as a clash (`own_allocation_sources`);
- Category rows: lines must be of the allocated item; Category and Quantity rows cap how many units
  run at the same time (`qty`);
- Capacity and Provider-time rows: booked hours (hours x qty) consume `capacity`; hours above it are
  overage, billed as a Billable Event at the contract's `overage_rate` per hour. Cancelling a
  booking gives its hours back (and cancels an overage event that is not invoiced yet).
- The row's `rate_override` replaces the rate card price per billing unit.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

from frappe_rental.services import billable_events

LIVE = ("Reserved", "Active")


def _row(doc):
	if not (doc.get("rental_contract") and doc.get("contract_allocation")):
		return None
	row = frappe.db.get_value(
		"Rental Contract Allocation",
		{"name": doc.contract_allocation, "parent": doc.rental_contract, "parenttype": "Rental Contract"},
		["*"],
		as_dict=True,
	)
	if not row:
		frappe.throw(
			_("Allocation {0} is not on contract {1}").format(doc.contract_allocation, doc.rental_contract)
		)
	return row


def own_allocation_sources(doc, line) -> list[tuple[str, str]]:
	row = _row(doc) if doc.get("contract_allocation") else None
	if row and row.rental_unit and row.rental_unit == line.rental_unit:
		return [("Rental Contract", doc.rental_contract)]
	return []


def hours(doc) -> float:
	total = 0.0
	for line in doc.lines:
		start = get_datetime(line.from_datetime or doc.from_datetime)
		end = get_datetime(line.to_datetime or doc.to_datetime)
		total += (end - start).total_seconds() / 3600 * flt(line.qty or 1)
	return flt(total, 2)


def validate(doc) -> None:
	"""Booking validate, after pricing: contract checks, unit and item rules, rate override."""
	if not doc.get("rental_contract"):
		return
	contract = frappe.db.get_value(
		"Rental Contract",
		doc.rental_contract,
		["status", "customer", "start_date", "end_date", "open_ended"],
		as_dict=True,
	)
	if contract.status != "Active":
		frappe.throw(_("Contract {0} is not active").format(doc.rental_contract))
	if contract.customer != doc.customer:
		frappe.throw(_("Contract {0} belongs to another customer").format(doc.rental_contract))
	row = _row(doc)
	if not row:
		return
	if row.status not in LIVE:
		frappe.throw(_("Allocation {0} is {1}").format(row.name, _(row.status)))
	start, end = getdate(doc.from_datetime), getdate(doc.to_datetime)
	row_from = getdate(row.from_date or contract.start_date)
	row_to = row.to_date or (None if contract.open_ended else contract.end_date)
	if start < row_from or (row_to and end > getdate(row_to)):
		frappe.throw(_("The booking falls outside allocation {0}").format(row.name))
	for line in doc.lines:
		if row.allocation_type in ("Specific unit", "Quantity"):
			line.rental_unit = line.rental_unit or row.rental_unit
			if line.rental_unit != row.rental_unit:
				frappe.throw(_("Row {0}: the allocation is for {1}").format(line.idx, row.rental_unit))
		elif row.allocation_type == "Category" and row.rental_item and line.rental_item != row.rental_item:
			frappe.throw(_("Row {0}: the allocation is for {1}").format(line.idx, row.rental_item))
	if flt(row.rate_override):
		_apply_rate(doc, flt(row.rate_override))


def _apply_rate(doc, rate: float) -> None:
	from frappe_rental.services.booking import _precision, deposit_amount, tax_rate

	precision = _precision(doc)
	for line in doc.lines:
		line.rate = rate
		line.discount_amount = 0
		line.amount = flt(rate * flt(line.units) * flt(line.qty or 1), precision)
		line.applied_rule = _("Contract rate")
	doc.net_total = flt(
		sum(flt(ln.amount) for ln in doc.lines) + sum(flt(c.amount) for c in doc.charges), precision
	)
	doc.total_taxes = flt(doc.net_total * tax_rate(doc.taxes_and_charges) / 100, precision)
	doc.grand_total = flt(doc.net_total + doc.total_taxes, precision)
	doc.deposit_required = deposit_amount(doc.rental_type, doc.grand_total, precision)
	doc.balance = flt(doc.grand_total - flt(doc.deposit_paid), precision)


def _concurrent_qty(doc, row) -> float:
	rows = frappe.db.sql(
		"""select sum(l.qty) from `tabRental Booking Line` l join `tabRental Booking` b on b.name = l.parent
		where b.contract_allocation = %(row)s and b.docstatus = 1 and b.name != %(name)s
		and b.from_datetime < %(end)s and b.to_datetime > %(start)s""",
		{"row": row.name, "name": doc.name, "start": doc.from_datetime, "end": doc.to_datetime},
	)
	return flt(rows[0][0]) if rows else 0.0


def before_submit(doc) -> None:
	row = _row(doc)
	if not row:
		return
	frappe.db.sql("select name from `tabRental Contract Allocation` where name=%s for update", row.name)
	if row.allocation_type in ("Category", "Quantity"):
		wanted = sum(flt(ln.qty or 1) for ln in doc.lines)
		if _concurrent_qty(doc, row) + wanted > flt(row.qty):
			frappe.throw(_("Allocation {0} allows {1} at a time").format(row.name, flt(row.qty)))


def on_submit(doc) -> None:
	row = _row(doc)
	if not row or row.allocation_type not in ("Capacity", "Provider time"):
		return
	used_before = flt(frappe.db.get_value("Rental Contract Allocation", row.name, "capacity_used"))
	booked = hours(doc)
	frappe.db.set_value("Rental Contract Allocation", row.name, "capacity_used", used_before + booked)
	over = max(used_before + booked - flt(row.capacity), 0) - max(used_before - flt(row.capacity), 0)
	rate = flt(frappe.db.get_value("Rental Contract", doc.rental_contract, "overage_rate"))
	if over > 0 and rate:
		billable_events.add(
			doc.name,
			"Other",
			flt(over * rate, 2),
			description=_("Overage: {0} hours above the allowance of {1}").format(flt(over, 2), row.capacity),
			source=doc,
		)


def on_cancel(doc) -> None:
	row = _row(doc)
	if not row or row.allocation_type not in ("Capacity", "Provider time"):
		return
	used = flt(frappe.db.get_value("Rental Contract Allocation", row.name, "capacity_used"))
	frappe.db.set_value("Rental Contract Allocation", row.name, "capacity_used", max(used - hours(doc), 0))
	for name in frappe.get_all(
		"Rental Billable Event", filters={"source_name": doc.name, "status": "Pending"}, pluck="name"
	):
		frappe.db.set_value("Rental Billable Event", name, "status", "Cancelled")


def remaining(contract: str, row_name: str) -> float:
	row = frappe.db.get_value(
		"Rental Contract Allocation", row_name, ["capacity", "capacity_used", "parent"], as_dict=True
	)
	if not row or row.parent != contract:
		frappe.throw(_("Allocation not found"))
	return flt(flt(row.capacity) - flt(row.capacity_used), 2)
