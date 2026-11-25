"""Validation for rate cards, charges, deposit rules, seasons and cancellation policies (T10).

`find_overlap` is pure so the rule can be unit tested without the database: two rate rows clash when
they would both match the same booking at the same priority, which would make pricing ambiguous.
"""

import re
from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, getdate

MASK_RE = re.compile(r"^[01]{7}$")
FAR_PAST = date(1900, 1, 1)
FAR_FUTURE = date(9999, 12, 31)


def validate_season(doc) -> None:
	if getdate(doc.from_date) > getdate(doc.to_date):
		frappe.throw(_("Season {0}: From must be on or before To").format(doc.season_name))


def validate_rate_card(doc) -> None:
	for row in doc.rates or []:
		row.weekday_mask = row.weekday_mask or "1111111"
		if not MASK_RE.match(row.weekday_mask) or "1" not in row.weekday_mask:
			frappe.throw(
				_("Row {0}: weekday mask must be 7 digits of 0 or 1 with at least one 1").format(row.idx)
			)
		if flt(row.rate) < 0:
			frappe.throw(_("Row {0}: rate cannot be negative").format(row.idx))
		if flt(row.min_units) < 0 or flt(row.max_units) < 0:
			frappe.throw(_("Row {0}: unit limits cannot be negative").format(row.idx))
		if flt(row.max_units) and flt(row.min_units) >= flt(row.max_units):
			frappe.throw(_("Row {0}: Min Units must be below Max Units").format(row.idx))
		if row.valid_from and row.valid_to and getdate(row.valid_from) > getdate(row.valid_to):
			frappe.throw(_("Row {0}: Valid From must be on or before Valid To").format(row.idx))
	clash = find_overlap([_rate_dict(r) for r in doc.rates or []])
	if clash:
		frappe.throw(
			_(
				"Rows {0} and {1} overlap at the same priority; change the priority or narrow one of them"
			).format(*clash)
		)
	if doc.rounding_mode == "Minimum charge" and flt(doc.minimum_charge) <= 0:
		frappe.throw(_("Minimum Charge must be greater than zero for rounding mode Minimum charge"))
	seen = set()
	for row in doc.charges or []:
		if row.charge in seen:
			frappe.throw(_("Charge {0} is listed twice").format(row.charge))
		seen.add(row.charge)


def find_overlap(rows: list[dict]) -> tuple[int, int] | None:
	"""Return the idx pair of the first two clashing rows, or None.

	Each row: idx, time_unit, priority, min_units, max_units (0 = open), valid_from, valid_to,
	weekday_mask, season, customer_group, rental_unit. Seasons are compared by name: two different
	seasons are treated as disjoint, which is their purpose.
	"""
	for i, a in enumerate(rows):
		for b in rows[i + 1 :]:
			if _clash(a, b):
				return a["idx"], b["idx"]
	return None


def _clash(a: dict, b: dict) -> bool:
	for key in ("time_unit", "season", "customer_group", "rental_unit"):
		if (a.get(key) or None) != (b.get(key) or None):
			return False
	if int(a.get("priority") or 0) != int(b.get("priority") or 0):
		return False
	if not any(
		x == y == "1"
		for x, y in zip(a.get("weekday_mask") or "1111111", b.get("weekday_mask") or "1111111", strict=False)
	):
		return False
	a_from, a_to = _dates(a)
	b_from, b_to = _dates(b)
	if a_from > b_to or b_from > a_to:
		return False
	return _ranges_overlap(
		flt(a.get("min_units")), flt(a.get("max_units")), flt(b.get("min_units")), flt(b.get("max_units"))
	)


def _dates(row: dict) -> tuple[date, date]:
	start = getdate(row["valid_from"]) if row.get("valid_from") else FAR_PAST
	end = getdate(row["valid_to"]) if row.get("valid_to") else FAR_FUTURE
	return start, end


def _ranges_overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> bool:
	"""Half-open unit ranges [min, max); max 0 means no upper limit."""
	a_hi = a_max or float("inf")
	b_hi = b_max or float("inf")
	return a_min < b_hi and b_min < a_hi


def _rate_dict(row) -> dict:
	fields = (
		"idx",
		"time_unit",
		"priority",
		"min_units",
		"max_units",
		"valid_from",
		"valid_to",
		"weekday_mask",
		"season",
		"customer_group",
		"rental_unit",
	)
	return {f: row.get(f) for f in fields}


def validate_charge(doc) -> None:
	if doc.charge_type == "Percent":
		if not 0 < flt(doc.percent) <= 100:
			frappe.throw(_("Percent must be between 0 and 100"))
	elif flt(doc.amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))


def validate_deposit_rule(doc) -> None:
	if doc.deposit_type == "Percent":
		if not 0 < flt(doc.percent) <= 100:
			frappe.throw(_("Percent must be between 0 and 100"))
	elif flt(doc.amount) <= 0:
		frappe.throw(_("Amount must be greater than zero"))
	if doc.liability_account:
		root_type = frappe.db.get_value("Account", doc.liability_account, "root_type")
		if root_type != "Liability":
			frappe.throw(_("Deposit account {0} must be a liability account").format(doc.liability_account))


def validate_cancellation_policy(doc) -> None:
	seen = set()
	for row in doc.tiers or []:
		if flt(row.hours_before_start) < 0:
			frappe.throw(_("Row {0}: hours cannot be negative").format(row.idx))
		if not 0 <= flt(row.refund_percent) <= 100:
			frappe.throw(_("Row {0}: refund must be between 0 and 100 percent").format(row.idx))
		if flt(row.fee) < 0:
			frappe.throw(_("Row {0}: fee cannot be negative").format(row.idx))
		if flt(row.hours_before_start) in seen:
			frappe.throw(_("Row {0}: duplicate tier for {1} hours").format(row.idx, row.hours_before_start))
		seen.add(flt(row.hours_before_start))
	doc.tiers.sort(key=lambda r: -flt(r.hours_before_start))
	for i, row in enumerate(doc.tiers, 1):
		row.idx = i
