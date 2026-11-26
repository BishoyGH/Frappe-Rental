"""Staff operations endpoints (T29): handover screen, billing tab, deposit and damage panels."""

import json

import frappe
from frappe import _

from frappe_rental.services import damage, staff_ops


def _booking(name: str, ptype: str = "read"):
	if not name or not frappe.db.exists("Rental Booking", name):
		frappe.throw(_("Booking {0} not found").format(name), frappe.DoesNotExistError)
	doc = frappe.get_doc("Rental Booking", name)
	if not frappe.has_permission("Rental Booking", ptype, doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["GET", "POST"])
def find_booking(code: str) -> dict | None:
	"""Scan-first lookup: a booking name, unit barcode, serial or external ID."""
	if not frappe.has_permission("Rental Handover", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = staff_ops.find_booking(code)
	if not name or not frappe.has_permission("Rental Booking", "read", name):
		return None
	return staff_ops.handover_state(frappe.get_doc("Rental Booking", name))


@frappe.whitelist(methods=["GET", "POST"])
def handover_state(name: str) -> dict:
	return staff_ops.handover_state(_booking(name))


@frappe.whitelist(methods=["GET", "POST"])
def todays_handovers() -> dict:
	"""Bookings to hand out or take back today (and anything overdue)."""
	if not frappe.has_permission("Rental Booking", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	today = frappe.utils.nowdate()
	fields = ["name", "customer", "status", "from_datetime", "to_datetime"]
	outgoing = frappe.get_list(
		"Rental Booking",
		filters={
			"docstatus": 1,
			"status": "Confirmed",
			"from_datetime": ["<", frappe.utils.add_days(today, 1)],
		},
		fields=fields,
		order_by="from_datetime asc",
		limit_page_length=100,
	)
	incoming = frappe.get_list(
		"Rental Booking",
		filters={
			"docstatus": 1,
			"status": "Checked Out",
			"to_datetime": ["<", frappe.utils.add_days(today, 1)],
		},
		fields=fields,
		order_by="to_datetime asc",
		limit_page_length=100,
	)
	return {"outgoing": outgoing, "incoming": incoming}


@frappe.whitelist(methods=["GET", "POST"])
def billing(name: str) -> dict:
	return staff_ops.billing(_booking(name))


@frappe.whitelist(methods=["POST"])
def save_schedule(name: str, rows: str | list) -> dict:
	data = json.loads(rows) if isinstance(rows, str) else rows
	if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
		frappe.throw(_("Rows must be a list of objects"))
	return staff_ops.save_schedule(_booking(name, "write"), data)


@frappe.whitelist(methods=["GET", "POST"])
def panels(name: str) -> dict:
	return staff_ops.panels(_booking(name))


def _damage(name: str):
	if not frappe.db.exists("Rental Damage Report", name):
		frappe.throw(_("Damage report {0} not found").format(name), frappe.DoesNotExistError)
	if not frappe.has_permission("Rental Damage Report", "write", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return name


@frappe.whitelist(methods=["POST"])
def approve_damage(name: str, amount: float | None = None) -> dict:
	damage.approve(_damage(name), amount)
	return frappe.get_doc("Rental Damage Report", name).as_dict()


@frappe.whitelist(methods=["POST"])
def settle_damage(name: str, method: str) -> dict:
	if method not in ("Deposit", "Invoice", "Write-off"):
		frappe.throw(_("Settle by Deposit, Invoice or Write-off"))
	posted = damage.settle(_damage(name), method)
	return {
		"name": name,
		"posted": posted,
		"status": frappe.db.get_value("Rental Damage Report", name, "status"),
	}
