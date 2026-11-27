"""Payment endpoints (T33, REST v1).

``create_request`` asks the customer to pay a booking's invoice through an ERPNext Payment Request. The
gateway callback belongs to the payment gateway app (ERPNext's Payment Request already handles the
gateway's completion hook), so no rental-specific callback endpoint is needed.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from frappe_rental.compat import erpnext as compat
from frappe_rental.services.idempotency import idempotent


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
@idempotent
def create_request(name: str, idempotency_key: str | None = None) -> dict:
	"""A submitted Payment Request for the booking's open invoice. Returns the existing open one if any."""
	booking = frappe.get_doc("Rental Booking", name)
	if not frappe.has_permission("Rental Booking", "read", booking) or not frappe.has_permission(
		"Payment Request", "create"
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	invoice = booking.get("sales_invoice")
	if not invoice or frappe.db.get_value("Sales Invoice", invoice, "docstatus") != 1:
		frappe.throw(_("Booking {0} has no submitted invoice to pay").format(name))
	if not frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount"):
		frappe.throw(_("Invoice {0} is already paid").format(invoice))
	existing = frappe.db.get_value(
		"Payment Request",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice,
			"docstatus": 1,
			"status": ["not in", ["Paid", "Cancelled"]],
		},
	)
	pr = existing or compat.make_payment_request("Sales Invoice", invoice)
	row = frappe.db.get_value(
		"Payment Request", pr, ["name", "grand_total", "currency", "status", "payment_url"], as_dict=True
	)
	return {**row, "sales_invoice": invoice, "booking": name}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def stripe_webhook() -> dict:
	"""Stripe webhook. Trust comes from the signature checked in ``services.payments``, not the session."""
	from frappe_rental.services import checkout, payments

	payload = frappe.request.get_data() if frappe.request else b""
	with checkout._as_system():  # signature verified before anything is posted
		return payments.handle_webhook("Stripe", payload, frappe.request.headers)
