"""Deposit API (T25). Validates, checks permission on the deposit, then calls services.deposits."""

import frappe
from frappe import _

from frappe_rental.services import deposits


def _deposit(name: str):
	if not name or not frappe.db.exists("Rental Deposit", name):
		frappe.throw(_("Deposit {0} not found").format(name), frappe.DoesNotExistError)
	if not frappe.has_permission("Rental Deposit", "write", name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return name


def _state(name: str) -> dict:
	doc = frappe.get_doc("Rental Deposit", name)
	return {
		"name": doc.name,
		"status": doc.status,
		"amount_required": doc.amount_required,
		"amount_received": doc.amount_received,
		"balance_held": doc.balance_held,
		"entries": [e.as_dict() for e in doc.entries],
	}


@frappe.whitelist(methods=["POST"])
def request(booking: str) -> dict | None:
	if not frappe.has_permission("Rental Booking", "write", booking):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	name = deposits.request(frappe.get_doc("Rental Booking", booking))
	return _state(name) if name else None


@frappe.whitelist(methods=["POST"])
def collect(
	deposit: str, amount: float, mode_of_payment: str | None = None, reference: str | None = None
) -> dict:
	deposits.collect(_deposit(deposit), amount, mode_of_payment=mode_of_payment, reference=reference)
	return _state(deposit)


@frappe.whitelist(methods=["POST"])
def settle(deposit: str, action: str, amount: float | None = None, sales_invoice: str | None = None) -> dict:
	"""action: refund | apply | forfeit. Empty amount settles the whole held balance."""
	_deposit(deposit)
	if action == "refund":
		deposits.refund(deposit, amount)
	elif action == "apply":
		deposits.apply(deposit, amount, sales_invoice=sales_invoice)
	elif action == "forfeit":
		deposits.forfeit(deposit, amount)
	else:
		frappe.throw(_("Unknown settlement {0}").format(action))
	return _state(deposit)
