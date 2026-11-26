"""Provider scheduling API (T45): free slots and the signed-in provider's own schedule."""

import frappe
from frappe import _
from frappe.utils import add_days, nowdate

from frappe_rental.services import provider


@frappe.whitelist(methods=["GET", "POST"])
def slots(unit: str, from_date: str, to_date: str | None = None, minutes: int = 60) -> list[dict]:
	if not frappe.has_permission("Rental Unit", "read", unit):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return provider.slots(unit, from_date, to_date, int(minutes or 60))


@frappe.whitelist(methods=["GET", "POST"])
def my_schedule(from_date: str | None = None, to_date: str | None = None) -> list[dict]:
	"""Bookings of the caller's own Provider units (Employee.user_id), next 14 days by default."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from_date = from_date or nowdate()
	return provider.my_schedule(frappe.session.user, from_date, to_date or add_days(from_date, 14))
