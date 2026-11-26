"""Waitlist and substitution endpoints (T52)."""

import frappe
from frappe import _

from frappe_rental.services import waitlist as service


@frappe.whitelist(methods=["POST"])
def add(
	customer: str,
	rental_item: str,
	from_datetime: str,
	to_datetime: str,
	qty: float = 1,
	rental_unit: str | None = None,
	notes: str | None = None,
) -> str:
	"""Put a customer on the waitlist for an item (or one unit) and period."""
	if not frappe.has_permission(service.DOCTYPE, "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return service.add(customer, rental_item, from_datetime, to_datetime, float(qty or 1), rental_unit, notes)


@frappe.whitelist(methods=["GET", "POST"])
def substitutes(rental_item: str, from_datetime: str, to_datetime: str, qty: float = 1) -> dict:
	"""Free alternatives when the requested item clashes."""
	if not frappe.has_permission("Rental Unit", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return service.substitutes(rental_item, from_datetime, to_datetime, float(qty or 1))


@frappe.whitelist(methods=["GET", "POST"])
def get_list(status: str | None = "Waiting", rental_item: str | None = None) -> list[dict]:
	if not frappe.has_permission(service.DOCTYPE, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {k: v for k, v in {"status": status, "rental_item": rental_item}.items() if v}
	return frappe.get_list(
		service.DOCTYPE,
		filters=filters,
		fields=[
			"name",
			"customer",
			"rental_item",
			"rental_unit",
			"from_datetime",
			"to_datetime",
			"qty",
			"status",
		],
		order_by="from_datetime asc",
		limit_page_length=200,
	)
