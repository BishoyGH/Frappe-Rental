import frappe
from frappe import _

from frappe_rental.services import unit as unit_service


@frappe.whitelist()
def lookup(identifier: str) -> dict | None:
	"""Find a Rental Unit by unit code, barcode, serial, batch, asset or external id."""
	if not isinstance(identifier, str) or not identifier.strip():
		frappe.throw(_("Identifier is required"))
	if not frappe.has_permission("Rental Unit", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = unit_service.find_unit(identifier)
	if not name or not frappe.has_permission("Rental Unit", "read", doc=name):
		return None
	return frappe.db.get_value(
		"Rental Unit", name, ["name", "unit_name", "rental_item", "status", "location"], as_dict=True
	)
