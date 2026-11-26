"""Contract allocations (T42, D7): resources assigned to a contract, wired into availability.

- Exclusive rows with a unit (Specific unit, or Quantity of a pooled unit) write Rental Availability
  Cache rows with source Rental Contract, so search, calendar and bookings never offer them.
- Category, Capacity and Provider-time rows are entitlements: no cache rows; call-off bookings (T43)
  consume them.
- Over-allocation guard: a unit that is booked, blocked or allocated elsewhere in the period cannot
  be allocated; pooled rows cannot exceed free stock. Checked under the unit row lock.
- Changes with an effective date: `add`, `release` (row ends the day before), `swap` (old row
  Swapped up to the day before, new row from the date, reason kept). Each rewrites the contract's
  cache rows. Bookings and billing under the contract follow in T43/T44.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate

from frappe_rental.services import availability

SOURCE = "Rental Contract"
LIVE = ("Reserved", "Active")
ENDED = ("Swapped", "Released")  # still hold the unit up to their to_date
CACHED_TYPES = ("Specific unit", "Quantity")


def _window(contract, row):
	start = get_datetime(row.from_date or contract.start_date)
	end_date = row.to_date or (None if contract.open_ended else contract.end_date)
	end = get_datetime(add_days(end_date, 1)) if end_date else None
	return start, end


def validate_rows(contract) -> None:
	for row in contract.get("allocations") or []:
		if row.allocation_type in CACHED_TYPES and not row.rental_unit:
			frappe.throw(_("Row {0}: choose the unit").format(row.idx))
		if row.allocation_type == "Category" and not (row.rental_item or row.rental_unit):
			frappe.throw(_("Row {0}: choose the item for a category allocation").format(row.idx))
		if row.allocation_type in ("Capacity", "Provider time") and not row.capacity:
			frappe.throw(_("Row {0}: set the capacity").format(row.idx))
		if row.from_date and row.to_date and getdate(row.to_date) < getdate(row.from_date):
			frappe.throw(_("Row {0}: ends before it starts").format(row.idx))
		if row.rental_unit and not row.rental_item:
			row.rental_item = frappe.db.get_value("Rental Unit", row.rental_unit, "rental_item")


def reserve(contract) -> None:
	"""Rewrite the contract's cache rows from its live exclusive allocations. Raises on a conflict."""
	rows = [
		r
		for r in contract.allocations
		if (r.status in LIVE or (r.status in ENDED and r.to_date))
		and r.exclusive
		and r.allocation_type in CACHED_TYPES
	]
	for unit in sorted({r.rental_unit for r in rows}):
		availability.lock_unit(unit)
	availability.release(SOURCE, contract.name)
	for row in rows:
		start, end = _window(contract, row)
		qty = row.qty if row.allocation_type == "Quantity" else 1
		# the row's own call-off bookings sit on the same unit by design and are not a clash
		own = [
			("Rental Booking", b)
			for b in frappe.get_all(
				"Rental Booking",
				filters={"contract_allocation": row.name, "docstatus": ["<", 2]},
				pluck="name",
			)
		]
		if not availability.is_available(
			row.rental_unit, start, end, qty, exclude=[(SOURCE, contract.name), *own], locking=True
		):
			frappe.throw(
				_("Row {0}: {1} is booked, blocked or allocated in that period").format(
					row.idx, row.rental_unit
				),
				availability.UnavailableError
				if hasattr(availability, "UnavailableError")
				else frappe.ValidationError,
			)
		availability._insert(row.rental_unit, start, end, qty, SOURCE, contract.name, row.name)
	# rows of the same contract may not overlap each other either
	for i, a in enumerate(rows):
		for b in rows[i + 1 :]:
			if (
				a.rental_unit == b.rental_unit
				and a.allocation_type == "Specific unit"
				and _overlap(contract, a, b)
			):
				frappe.throw(_("Rows {0} and {1} allocate {2} twice").format(a.idx, b.idx, a.rental_unit))


def _overlap(contract, a, b) -> bool:
	a0, a1 = _window(contract, a)
	b0, b1 = _window(contract, b)
	return a0 < (b1 or get_datetime("9999-12-31")) and b0 < (a1 or get_datetime("9999-12-31"))


def release_all(contract) -> None:
	availability.release(SOURCE, contract.name)


def _save(contract) -> None:
	contract.flags.amending = True  # allocation changes are operational, recorded per row
	contract.save()
	if contract.status in ("Active", "Suspended", "Ending"):
		reserve(contract)


def add(contract, row: dict, effective_date=None) -> str:
	row = {**row, "from_date": row.get("from_date") or effective_date or contract.start_date}
	new = contract.append(
		"allocations", {"status": "Active" if contract.status == "Active" else "Reserved", **row}
	)
	_save(contract)
	return new.name


def release(contract, row_name: str, effective_date) -> None:
	row = _row(contract, row_name)
	row.to_date = add_days(effective_date, -1)
	row.status = "Released"
	row.change_reason = _("Released from {0}").format(effective_date)
	_save(contract)


def swap(contract, row_name: str, new_unit: str, effective_date, reason: str) -> str:
	if not reason:
		frappe.throw(_("Give a reason for the swap"))
	old = _row(contract, row_name)
	if old.status not in LIVE:
		frappe.throw(_("Only a live allocation can be swapped"))
	new = contract.append(
		"allocations",
		{
			"allocation_type": old.allocation_type,
			"rental_unit": new_unit,
			"rental_item": frappe.db.get_value("Rental Unit", new_unit, "rental_item"),
			"from_date": effective_date,
			"to_date": old.to_date,
			"qty": old.qty,
			"exclusive": old.exclusive,
			"rate_override": old.rate_override,
			"site": old.site,
			"status": old.status,
			"substitution_allowed": old.substitution_allowed,
			"swapped_from": old.name,
			"change_reason": reason,
		},
	)
	old.to_date = add_days(effective_date, -1)
	old.status = "Swapped"
	old.change_reason = reason
	_save(contract)
	return new.name


def _row(contract, name):
	for row in contract.allocations:
		if row.name == name:
			return row
	frappe.throw(_("Allocation {0} not found").format(name))
