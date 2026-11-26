"""Housekeeping API (T51): open turnaround tasks and completing one (staff app, cleaner's phone)."""

import frappe
from frappe import _

from frappe_rental.services import housekeeping


@frappe.whitelist()
def open_tasks(location: str | None = None) -> list[dict]:
	if not frappe.has_permission(housekeeping.DOCTYPE, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {"status": ["not in", housekeeping.CLOSED]}
	if location:
		units = frappe.get_all("Rental Unit", filters={"location": location}, pluck="name")
		filters["rental_unit"] = ["in", units or [""]]
	return frappe.get_list(
		housekeeping.DOCTYPE,
		filters=filters,
		fields=["name", "rental_unit", "task_type", "status", "due_by", "assigned_to", "rental_booking"],
		order_by="due_by asc",
	)


@frappe.whitelist(methods=["POST"])
def complete(name: str, notes: str | None = None) -> dict:
	if not frappe.has_permission(housekeeping.DOCTYPE, "write", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	housekeeping.complete(name, notes)
	return {"status": "Done"}
