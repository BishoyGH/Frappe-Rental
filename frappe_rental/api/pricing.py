"""Pricing endpoint (T33, REST v1)."""

import json

import frappe
from frappe import _

from frappe_rental.api import booking as booking_api


@frappe.whitelist(methods=["GET", "POST"])
def quote(
	items: str | list,
	from_datetime: str,
	to_datetime: str,
	rental_type: str | None = None,
	customer: str | None = None,
	location: str | None = None,
	coupon: str | None = None,
) -> dict:
	"""Price items for a period without saving anything. ``items`` is a list of
	``{"rental_item", "rental_unit"?, "qty"?}``. Returns lines, charges and totals."""
	rows = json.loads(items) if isinstance(items, str) else items
	if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
		frappe.throw(_("Items must be a non-empty list of objects"))
	lines = [{k: r.get(k) for k in ("rental_item", "rental_unit", "qty") if r.get(k)} for r in rows]
	if not rental_type:
		rental_type = frappe.db.get_value("Rental Item", lines[0].get("rental_item"), "rental_type")
	booking = {
		"rental_type": rental_type,
		"customer": customer,
		"location": location,
		"from_datetime": from_datetime,
		"to_datetime": to_datetime,
		"coupon_code": coupon,
		"lines": lines,
	}
	return booking_api.quote({k: v for k, v in booking.items() if v})
