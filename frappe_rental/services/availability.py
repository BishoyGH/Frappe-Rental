"""Availability (T13): busy windows per unit and the overlap rules.

Every booking line and Rental Block that holds a unit writes rows to Rental Availability Cache
(busy_from/busy_to include the Rental Type buffers; an empty busy_to is open-ended). Ranges are
half-open, so a booking ending at 10:00 and another starting at 10:00 do not clash.

Exclusive units allow one overlapping row. Pooled units allow overlapping rows as long as the peak
concurrent quantity stays within `quantity_available`. Writers lock the unit row (SELECT ... FOR
UPDATE) before checking, so two parallel requests for the same unit serialise and the second sees
the first one's rows.
"""

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

CACHE = "Rental Availability Cache"
FAR_FUTURE = datetime(9999, 12, 31)
UNAVAILABLE_STATUSES = ("Maintenance", "Blocked", "Retired")


class UnavailableError(frappe.ValidationError):
	pass


def validate_range(start, end) -> None:
	if end and get_datetime(end) <= get_datetime(start):
		frappe.throw(_("To must be after From"))


def busy_window(start, end, rental_type: str | None) -> tuple[datetime, datetime | None]:
	before, after = 0, 0
	if rental_type:
		before, after = frappe.db.get_value(
			"Rental Type", rental_type, ["buffer_before", "buffer_after"]
		) or (0, 0)
	start = get_datetime(start) - timedelta(minutes=int(before or 0))
	end = get_datetime(end) + timedelta(minutes=int(after or 0)) if end else None
	return start, end


def overlapping_rows(
	unit: str,
	start: datetime,
	end: datetime | None,
	exclude: tuple[str, str] | None = None,
	locking: bool = False,
) -> list[dict]:
	"""Cache rows for `unit` whose window intersects [start, end).

	`locking` makes it a locking read, which sees rows committed after this transaction's snapshot;
	writers need that, because a plain read under REPEATABLE READ can miss a parallel writer's rows.
	"""
	end_value = end or FAR_FUTURE
	conditions = ["rental_unit = %(unit)s", "busy_from < %(end)s", "(busy_to is null or busy_to > %(start)s)"]
	values = {"unit": unit, "start": start, "end": end_value}
	if exclude:
		conditions.append("not (source_doctype = %(ex_dt)s and source_name = %(ex_name)s)")
		values.update(ex_dt=exclude[0], ex_name=exclude[1])
	return frappe.db.sql(
		f"select name, busy_from, busy_to, qty, source_doctype, source_name from `tab{CACHE}` where {' and '.join(conditions)}"
		+ (" for update" if locking else ""),
		values,
		as_dict=True,
	)


def peak_load(rows: list[dict], start: datetime, end: datetime | None) -> float:
	"""Highest concurrent qty of `rows` inside [start, end) (sweep line)."""
	end = end or FAR_FUTURE
	events = []
	for row in rows:
		events.append((max(get_datetime(row["busy_from"]), start), 1, flt(row["qty"])))
		events.append(
			(min(get_datetime(row["busy_to"]) if row["busy_to"] else FAR_FUTURE, end), 0, flt(row["qty"]))
		)
	load = peak = 0.0
	for _when, kind, qty in sorted(events):  # ends (0) sort before starts (1) at the same instant
		load += qty if kind else -qty
		peak = max(peak, load)
	return peak


def is_available(
	unit: str, start, end, qty: float = 1, rental_type: str | None = None, exclude=None, locking: bool = False
) -> bool:
	unit_doc = frappe.db.get_value(
		"Rental Unit", unit, ["status", "identification_mode", "quantity_available"], as_dict=True
	)
	if not unit_doc or unit_doc.status in UNAVAILABLE_STATUSES:
		return False
	busy_from, busy_to = busy_window(start, end, rental_type)
	rows = overlapping_rows(unit, busy_from, busy_to, exclude, locking)
	if unit_doc.identification_mode == "Pooled":
		return peak_load(rows, busy_from, busy_to) + flt(qty) <= flt(unit_doc.quantity_available)
	return not rows and flt(qty) <= 1


def lock_unit(unit: str) -> None:
	frappe.db.sql("select name from `tabRental Unit` where name = %s for update", unit)


def free_units(
	rental_item: str, start, end, qty: float = 1, rental_type: str | None = None, exclude=None
) -> list[str]:
	units = frappe.get_all(
		"Rental Unit",
		filters={"rental_item": rental_item, "is_group": 0, "status": ["not in", UNAVAILABLE_STATUSES]},
		pluck="name",
		order_by="name asc",
	)
	return [u for u in units if is_available(u, start, end, qty, rental_type, exclude)]


def reserve_booking(doc) -> None:
	"""Write cache rows for every line of a booking. Assigns a free unit to lines without one.

	Idempotent: the booking's previous rows are replaced. Raises UnavailableError on a clash.
	"""
	source = ("Rental Booking", doc.name)
	release(*source)
	for line in doc.lines:
		start = line.from_datetime or doc.from_datetime
		end = line.to_datetime or doc.to_datetime
		if not line.rental_unit:
			candidates = free_units(line.rental_item, start, end, line.qty, doc.rental_type, source)
			if not candidates:
				raise UnavailableError(_("Row {0}: no free unit of {1}").format(line.idx, line.rental_item))
			line.rental_unit = candidates[0]
			if line.name:
				line.db_set("rental_unit", line.rental_unit, update_modified=False)
		lock_unit(line.rental_unit)
		if not is_available(line.rental_unit, start, end, line.qty, doc.rental_type, source, locking=True):
			raise UnavailableError(
				_("Row {0}: unit {1} is not available for that period").format(line.idx, line.rental_unit)
			)
		_insert(line.rental_unit, *busy_window(start, end, doc.rental_type), line.qty, *source, line.name)


def reserve_block(block) -> None:
	release("Rental Block", block.name)
	lock_unit(block.rental_unit)
	_insert(
		block.rental_unit,
		get_datetime(block.from_datetime),
		get_datetime(block.to_datetime) if block.to_datetime else None,
		1e9,
		"Rental Block",
		block.name,
		None,
	)


def release(source_doctype: str, source_name: str) -> int:
	rows = frappe.get_all(
		CACHE, filters={"source_doctype": source_doctype, "source_name": source_name}, pluck="name"
	)
	for name in rows:
		frappe.db.delete(CACHE, {"name": name})
	return len(rows)


def _insert(unit, busy_from, busy_to, qty, source_doctype, source_name, source_row) -> None:
	row = frappe.get_doc(
		{
			"doctype": CACHE,
			"rental_unit": unit,
			"busy_from": busy_from,
			"busy_to": busy_to,
			"qty": qty,
			"source_doctype": source_doctype,
			"source_name": source_name,
			"source_row": source_row,
		}
	)
	row.flags.ignore_links = (
		True  # the source may still be unsaved when it reserves (e.g. a hold during validate)
	)
	row.insert(ignore_permissions=True)  # cache is system-maintained; callers already checked the source doc
