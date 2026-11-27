"""Pricing engine (T11, PLAN 4.3). `quote()` is a pure function: no database reads or writes.

Callers (booking form, API, portal) load the rate card and context into plain dicts and get a line
breakdown back, so every channel prices the same way.

Request keys:
  from_datetime, to_datetime  ISO string or datetime; naive values are UTC (how we store them)
  timezone                    Location timezone used for calendar units (Day, Week, Month, Year)
  qty                         units booked (default 1)
  uses                        count for the "Use" time unit (default 1)
  rental_unit, customer_group optional, for unit-specific and group rates
  seasons                     {season_name: (from_date, to_date)} for rows that name a season
  group_discount_pct          customer group discount (step 5)
  coupon_discount_pct         coupon discount (step 6), applied after the group discount
  tax_rate                    percent applied to the net total (step 8)
  precision                   currency precision (default 2)

Card keys: currency, rounding_mode ("Per started unit" | "Pro-rata" | "Minimum charge"),
minimum_charge, rates (Rental Rate rows as dicts), charges (Rental Charge dicts with is_mandatory).
"""

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from dateutil.relativedelta import relativedelta
from frappe.utils import flt, get_datetime, getdate

SECONDS = {"Minute": 60, "Hour": 3600}
CALENDAR_DAYS = {"Day": 1, "Week": 7}
MONTHS = {"Month": 1, "Year": 12}


class PricingError(ValueError):
	"""No rate applies, or the request is invalid."""


def quote(request: dict, card: dict, hooks: list | None = None) -> dict:
	start, end = _local_range(request)
	if end <= start:
		raise PricingError("to_datetime must be after from_datetime")
	precision = int(request.get("precision", 2))
	qty = flt(request.get("qty") or 1)
	if qty <= 0:
		raise PricingError("qty must be positive")

	choice = _choose_rate(request, card, start, end)
	if not choice:
		raise PricingError("No rate on the card matches this booking")
	row, units = choice

	base = flt(flt(row["rate"]) * units * qty, precision)
	if card.get("rounding_mode") == "Minimum charge":
		base = max(base, flt(card.get("minimum_charge"), precision))
	discount = _discount(base, request, precision)
	after_discount = flt(base - discount, precision)
	charges = _charges(card.get("charges") or [], after_discount, units, qty, precision)
	net = flt(after_discount + sum(c["amount"] for c in charges), precision)
	tax = flt(net * flt(request.get("tax_rate")) / 100, precision)
	result = {
		"currency": card.get("currency"),
		"time_unit": row["time_unit"],
		"units": units,
		"qty": qty,
		"rate": flt(row["rate"], precision),
		"base_amount": base,
		"discount_amount": discount,
		"charges": charges,
		"net_total": net,
		"tax_amount": tax,
		"grand_total": flt(net + tax, precision),
		"applied_rule": _describe(row),
	}
	for hook in hooks or []:
		result = hook(request, result) or result
	return result


def quote_with_hooks(request: dict, card: dict) -> dict:
	"""`quote` plus the `rental_pricing_hooks` registered by installed apps."""
	import frappe

	hooks = [frappe.get_attr(path) for path in frappe.get_hooks("rental_pricing_hooks")]
	return quote(request, card, hooks)


def billable_units(
	time_unit: str, start: datetime, end: datetime, request: dict, rounding_mode: str
) -> float:
	"""Units of `time_unit` between two local datetimes, rounded per the card's mode."""
	if time_unit == "Use":
		return flt(request.get("uses") or 1)
	if time_unit in SECONDS:
		exact = (_utc(end) - _utc(start)).total_seconds() / SECONDS[time_unit]
	elif time_unit in CALENDAR_DAYS:
		# Wall-clock difference, so a night across a DST change is still one night.
		wall = end.replace(tzinfo=None) - start.replace(tzinfo=None)
		exact = wall / timedelta(days=CALENDAR_DAYS[time_unit])
	elif time_unit in MONTHS:
		exact = _months_between(start.replace(tzinfo=None), end.replace(tzinfo=None)) / MONTHS[time_unit]
	else:
		raise PricingError(f"Unknown time unit {time_unit}")
	exact = round(exact, 6)  # absorb float noise before ceil
	if rounding_mode == "Per started unit" or not rounding_mode:
		return float(math.ceil(exact))
	return round(exact, 4)


def _months_between(start: datetime, end: datetime) -> float:
	months = (end.year - start.year) * 12 + (end.month - start.month)
	anchor = start + relativedelta(months=months)
	if anchor > end:
		months -= 1
		anchor = start + relativedelta(months=months)
	following = start + relativedelta(months=months + 1)
	return months + (end - anchor) / (following - anchor)


def _choose_rate(request, card, start, end):
	best = None
	for row in card.get("rates") or []:
		if not _matches(row, request, start):
			continue
		units = billable_units(row["time_unit"], start, end, request, card.get("rounding_mode"))
		if units < flt(row.get("min_units")) or (
			flt(row.get("max_units")) and units >= flt(row["max_units"])
		):
			continue
		amount = flt(row["rate"]) * units
		key = (int(row.get("priority") or 0), _specificity(row), -amount)
		if best is None or key > best[0]:
			best = (key, row, units)
	return (best[1], best[2]) if best else None


def _matches(row, request, start) -> bool:
	if row.get("rental_unit") and row["rental_unit"] != request.get("rental_unit"):
		return False
	if row.get("customer_group") and not _in_group(request.get("customer_group"), row["customer_group"]):
		return False
	day = start.date()
	if row.get("valid_from") and day < getdate(row["valid_from"]):
		return False
	if row.get("valid_to") and day > getdate(row["valid_to"]):
		return False
	mask = row.get("weekday_mask") or "1111111"
	if mask[day.weekday()] != "1":
		return False
	if row.get("season"):
		span = (request.get("seasons") or {}).get(row["season"])
		if not span or not getdate(span[0]) <= day <= getdate(span[1]):
			return False
	return True


def _in_group(group: str | None, parent: str) -> bool:
	"""True when ``group`` is ``parent`` or sits under it in the Customer Group tree.

	A rate for "All Customer Groups" (the tree root, which ERPNext also sets as the default on new
	rows) therefore applies to every customer.
	"""
	if group == parent:
		return True
	bounds = frappe.db.get_value("Customer Group", parent, ["lft", "rgt", "is_group"], as_dict=True)
	if not bounds or not bounds.is_group:
		return False
	if not group:
		return not frappe.db.get_value("Customer Group", parent, "parent_customer_group")
	lft = frappe.db.get_value("Customer Group", group, "lft")
	return bool(lft) and bounds.lft < lft < bounds.rgt


def _specificity(row) -> int:
	return 4 * bool(row.get("rental_unit")) + 2 * bool(row.get("customer_group")) + bool(row.get("season"))


def _discount(base, request, precision) -> float:
	group = flt(request.get("group_discount_pct"))
	coupon = flt(request.get("coupon_discount_pct"))
	for pct in (group, coupon):
		if not 0 <= pct <= 100:
			raise PricingError("discount percent must be between 0 and 100")
	after_group = base * (1 - group / 100)
	after_coupon = after_group * (1 - coupon / 100)
	return flt(base - after_coupon, precision)


def _charges(charges, after_discount, units, qty, precision) -> list[dict]:
	out = []
	for charge in charges:
		if not charge.get("is_mandatory", 1):
			continue
		if charge.get("charge_type") == "Percent":
			amount = after_discount * flt(charge.get("percent")) / 100
		elif charge.get("applies_per") == "Unit-Time":
			amount = flt(charge.get("amount")) * units * qty
		else:
			amount = flt(charge.get("amount"))
		out.append(
			{"charge": charge.get("charge_name") or charge.get("name"), "amount": flt(amount, precision)}
		)
	return out


def _describe(row) -> str:
	parts = [f"{row['time_unit']} @ {row['rate']}"]
	for key in ("rental_unit", "customer_group", "season"):
		if row.get(key):
			parts.append(f"{key}={row[key]}")
	if flt(row.get("min_units")) or flt(row.get("max_units")):
		parts.append(f"units {flt(row.get('min_units'))}-{flt(row.get('max_units')) or 'open'}")
	parts.append(f"priority {int(row.get('priority') or 0)}")
	return f"row {row.get('idx', '?')}: " + ", ".join(parts)


def _local_range(request) -> tuple[datetime, datetime]:
	tz = ZoneInfo(request.get("timezone") or "UTC")
	return _to_local(request["from_datetime"], tz), _to_local(request["to_datetime"], tz)


def _to_local(value, tz) -> datetime:
	dt = get_datetime(value)
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=UTC)
	return dt.astimezone(tz)


def _utc(dt: datetime) -> datetime:
	return dt.astimezone(UTC)


local_range = _local_range

__all__ = ["PricingError", "billable_units", "local_range", "quote", "quote_with_hooks"]
