"""Availability search and calendar (T15).

`search` finds free units for a period in a fixed number of queries, whatever the unit count:
one for candidate units, one for the cache rows that touch the widest busy window, one per Rental
Type for buffers. Overlap is then checked in memory with the same rules as `availability`.
Results are ranked by price (cheapest first), then units at the requested location, then name.
Prices come from `pricing.quote` once per Rental Item, not per unit.
"""

import calendar as pycalendar
from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from frappe_rental.services import availability, pricing
from frappe_rental.services import booking as booking_service

ITEM_FILTER_FIELDS = ("rental_type", "location", "is_published", "capacity_people")


def search(
	start,
	end,
	rental_type: str | None = None,
	rental_item: str | None = None,
	qty: float = 1,
	location: str | None = None,
	filters: dict | None = None,
	with_price: bool = True,
	limit: int | None = None,
) -> list[dict]:
	start, end = get_datetime(start), get_datetime(end)
	availability.validate_range(start, end)
	qty = flt(qty) or 1
	units = _candidate_units(rental_type, rental_item, location, filters)
	if not units:
		return []
	windows = _windows(start, end, {u.rental_type for u in units})
	rows = _cache_rows([u.name for u in units], windows)
	free = [u for u in units if _is_free(u, rows.get(u.name, []), windows[u.rental_type], qty)]
	prices = _prices({u.rental_item for u in free}, start, end, qty, location) if with_price else {}
	result = [
		{
			"rental_unit": u.name,
			"unit_name": u.unit_name,
			"rental_item": u.rental_item,
			"item_name": u.item_name,
			"rental_type": u.rental_type,
			"location": u.location,
			"free_qty": _free_qty(u, rows.get(u.name, []), windows[u.rental_type]),
			**prices.get(u.rental_item, {"price": None, "currency": None}),
		}
		for u in free
	]
	result.sort(
		key=lambda r: (
			r["price"] is None,
			flt(r["price"]),
			0 if location and r["location"] == location else 1,
			r["rental_unit"],
		)
	)
	return result[:limit] if limit else result


def calendar(year: int, month: int, rental_unit: str | None = None, rental_item: str | None = None) -> dict:
	"""Per day of the month: how many units are free all day, partly busy, or busy all day."""
	if not (rental_unit or rental_item):
		frappe.throw(_("A unit or an item is required"))
	if rental_unit:
		units = _candidate_units(None, None, None, None, unit=rental_unit)
	else:
		units = _candidate_units(None, rental_item, None, None)
	days = pycalendar.monthrange(int(year), int(month))[1]
	first = datetime(int(year), int(month), 1)
	last = first + timedelta(days=days)
	rows = _cache_rows([u.name for u in units], {None: (first, last)})
	out = {}
	for d in range(days):
		day_start = first + timedelta(days=d)
		day_end = day_start + timedelta(days=1)
		free = partial = busy = 0
		for u in units:
			urows = [r for r in rows.get(u.name, []) if _overlaps(r, day_start, day_end)]
			if not urows:
				free += 1
			elif _is_free(u, urows, (day_start, day_end), 1):
				partial += 1  # pooled with spare capacity counts as partly used
			elif _covers(urows, day_start, day_end):
				busy += 1
			else:
				partial += 1
		out[day_start.date().isoformat()] = {
			"free": free,
			"partial": partial,
			"busy": busy,
			"total": len(units),
		}
	return out


def _candidate_units(rental_type, rental_item, location, filters, unit=None) -> list:
	unit_t, item_t = frappe.qb.DocType("Rental Unit"), frappe.qb.DocType("Rental Item")
	query = (
		frappe.qb.from_(unit_t)
		.join(item_t)
		.on(item_t.name == unit_t.rental_item)
		.select(
			unit_t.name,
			unit_t.unit_name,
			unit_t.rental_item,
			unit_t.location,
			unit_t.identification_mode,
			unit_t.quantity_available,
			item_t.item_name,
			item_t.rental_type,
		)
		.where(unit_t.is_group == 0)
		.where(unit_t.status.notin(availability.UNAVAILABLE_STATUSES))
	)
	if unit:
		query = query.where(unit_t.name == unit)
	if rental_item:
		query = query.where(unit_t.rental_item == rental_item)
	if rental_type:
		query = query.where(item_t.rental_type == rental_type)
	if location:
		query = query.where(
			(unit_t.location == location) | (unit_t.location.isnull() & (item_t.location == location))
		)
	for field, value in (filters or {}).items():
		if field not in ITEM_FILTER_FIELDS:
			frappe.throw(_("Cannot filter on {0}").format(field))
		query = query.where(item_t[field] == value)
	return query.run(as_dict=True)


def _windows(start, end, types) -> dict:
	return {t: availability.busy_window(start, end, t) for t in types}


def _cache_rows(units: list[str], windows: dict) -> dict:
	lo = min(w[0] for w in windows.values())
	hi = max(w[1] or availability.FAR_FUTURE for w in windows.values())
	rows = defaultdict(list)
	for chunk in range(0, len(units), 1000):
		for row in frappe.db.sql(
			f"""select rental_unit, busy_from, busy_to, qty from `tab{availability.CACHE}`
			where rental_unit in %(units)s and busy_from < %(hi)s and (busy_to is null or busy_to > %(lo)s)""",
			{"units": tuple(units[chunk : chunk + 1000]), "lo": lo, "hi": hi},
			as_dict=True,
		):
			rows[row.rental_unit].append(row)
	return rows


def _overlaps(row, start, end) -> bool:
	return get_datetime(row.busy_from) < end and (not row.busy_to or get_datetime(row.busy_to) > start)


def _covers(rows, start, end) -> bool:
	return any(
		get_datetime(r.busy_from) <= start and (not r.busy_to or get_datetime(r.busy_to) >= end) for r in rows
	)


def _load(unit, rows, window) -> float:
	start, end = window
	return availability.peak_load(
		[r for r in rows if _overlaps(r, start, end or availability.FAR_FUTURE)], start, end
	)


def _is_free(unit, rows, window, qty) -> bool:
	if unit.identification_mode == "Pooled":
		return _load(unit, rows, window) + qty <= flt(unit.quantity_available)
	return qty <= 1 and _load(unit, rows, window) == 0


def _free_qty(unit, rows, window) -> float:
	cap = flt(unit.quantity_available) if unit.identification_mode == "Pooled" else 1
	return max(cap - _load(unit, rows, window), 0)


def _prices(items, start, end, qty, location) -> dict:
	timezone = location and frappe.db.get_value("Rental Location", location, "timezone")
	precision = booking_service._precision(None)
	out = {}
	for item in items:
		card_name = frappe.db.get_value("Rental Item", item, "rate_card")
		if not card_name:
			continue
		try:
			card = booking_service.load_rate_card(card_name)
			result = pricing.quote_with_hooks(
				{
					"from_datetime": start,
					"to_datetime": end,
					"timezone": timezone,
					"qty": qty,
					"seasons": card["seasons"],
					"precision": precision,
				},
				card,
			)
		except (pricing.PricingError, frappe.ValidationError):
			continue  # no applicable rate: listed without a price, ranked last
		total = (
			result["base_amount"] - result["discount_amount"] + sum(c["amount"] for c in result["charges"])
		)
		out[item] = {"price": flt(total, precision), "currency": card.get("currency")}
	return out
