"""Terms API (T39): live preview for the staff app."""

import frappe
from frappe import _

from frappe_rental.services import terms


@frappe.whitelist(methods=["GET", "POST"])
def preview(template: str, customer: str | None = None) -> dict:
	if not frappe.has_permission("Rental Terms Template", "read", template):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if customer and not frappe.has_permission("Customer", "read", customer):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return terms.render(template, terms.sample_context(customer))
