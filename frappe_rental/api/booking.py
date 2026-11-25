import json

import frappe
from frappe import _

from frappe_rental.services import booking as booking_service


@frappe.whitelist()
def quote(booking: str | dict) -> dict:
	"""Price a draft booking without saving it. Returns lines, charges and totals."""
	if not frappe.has_permission("Rental Booking", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	data = json.loads(booking) if isinstance(booking, str) else booking
	if not isinstance(data, dict) or not data.get("lines"):
		frappe.throw(_("A booking with at least one line is required"))
	data = {k: v for k, v in data.items() if k not in ("name", "docstatus", "doctype")}
	doc = frappe.get_doc({"doctype": "Rental Booking", **data})
	booking_service.validate_booking(doc)
	booking_service.apply_pricing(doc)
	return {
		"lines": [
			{
				f: line.get(f)
				for f in (
					"rental_item",
					"rental_unit",
					"qty",
					"time_unit",
					"units",
					"rate",
					"discount_amount",
					"amount",
					"applied_rule",
				)
			}
			for line in doc.lines
		],
		"charges": [{"charge": c.charge, "amount": c.amount} for c in doc.charges],
		**{
			f: doc.get(f) for f in ("currency", "net_total", "total_taxes", "grand_total", "deposit_required")
		},
	}
