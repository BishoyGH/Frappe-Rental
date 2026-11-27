"""Guest endpoints for the public website (T34). Published items only; rate limited per IP."""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from frappe_rental.services import public_site

LIMIT = 120  # per IP per minute


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=LIMIT, seconds=60)
def items(
	rental_type: str | None = None,
	location: str | None = None,
	qty: float = 1,
	from_datetime: str | None = None,
	to_datetime: str | None = None,
	guests: int | None = None,
	start: int = 0,
) -> dict:
	return public_site.list_items(rental_type, location, qty, from_datetime, to_datetime, start, guests)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=LIMIT, seconds=60)
def quote(item: str, from_datetime: str, to_datetime: str, qty: float = 1) -> dict:
	return public_site.quote(item, from_datetime, to_datetime, qty)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=LIMIT, seconds=60)
def calendar(item: str, month: str) -> dict:
	try:
		year, mon = (int(p) for p in month.split("-")[:2])
		assert 1 <= mon <= 12
	except (ValueError, AssertionError, AttributeError):
		frappe.throw(_("Month must look like 2026-05"))
	return public_site.calendar(item, year, mon)
