import json

import frappe
from frappe import _

from frappe_rental.services import search as search_service


def _check():
	if not frappe.has_permission("Rental Unit", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def search(
	from_datetime: str,
	to_datetime: str,
	rental_type: str | None = None,
	rental_item: str | None = None,
	qty: float = 1,
	location: str | None = None,
	filters: str | dict | None = None,
	limit: int | None = None,
) -> list[dict]:
	"""Free units for a period, cheapest first, with the computed price per item."""
	_check()
	if isinstance(filters, str):
		filters = json.loads(filters or "{}")
	if filters is not None and not isinstance(filters, dict):
		frappe.throw(_("Filters must be an object"))
	return search_service.search(
		from_datetime,
		to_datetime,
		rental_type=rental_type,
		rental_item=rental_item,
		qty=float(qty or 1),
		location=location,
		filters=filters,
		limit=int(limit) if limit else None,
	)


@frappe.whitelist(methods=["GET", "POST"])
def calendar(month: str, rental_unit: str | None = None, rental_item: str | None = None) -> dict:
	"""Day map for a month (`YYYY-MM`): free, partly busy and busy unit counts."""
	_check()
	try:
		year, mon = (int(p) for p in month.split("-")[:2])
		assert 1 <= mon <= 12
	except (ValueError, AssertionError, AttributeError):
		frappe.throw(_("Month must look like 2026-05"))
	return search_service.calendar(year, mon, rental_unit=rental_unit, rental_item=rental_item)
