import frappe
from frappe import _

from frappe_rental.services import rental_type as rental_type_service


@frappe.whitelist()
def install_presets() -> list[str]:
	"""Install the bundled Rental Type presets (button on the Rental Type list)."""
	if not frappe.has_permission("Rental Type", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return rental_type_service.install_presets()
