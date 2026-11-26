import json

import frappe
from frappe import _

from frappe_rental.services import booking as booking_service
from frappe_rental.services import lifecycle


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


def _get(name: str, ptype: str):
	if not isinstance(name, str) or not name:
		frappe.throw(_("A booking name is required"))
	doc = frappe.get_doc("Rental Booking", name)
	if not frappe.has_permission("Rental Booking", ptype, doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _state(doc) -> dict:
	return {"name": doc.name, "status": doc.status, "hold_expires_on": doc.hold_expires_on}


@frappe.whitelist(methods=["POST"])
def create_hold(name: str) -> dict:
	"""Hold a saved draft booking: reserve its units until the hold expires."""
	doc = _get(name, "write")
	lifecycle.place_hold(doc)
	return _state(doc)


@frappe.whitelist(methods=["POST"])
def confirm(name: str) -> dict:
	"""Confirm (submit) a booking after the deposit, contract and availability guards."""
	doc = _get(name, "submit")
	doc.submit()
	return _state(doc)


@frappe.whitelist(methods=["POST"])
def cancel(name: str) -> dict:
	"""Cancel a confirmed booking or release a hold."""
	doc = _get(name, "cancel" if frappe.db.get_value("Rental Booking", name, "docstatus") == 1 else "write")
	lifecycle.cancel(doc)
	return _state(doc)
