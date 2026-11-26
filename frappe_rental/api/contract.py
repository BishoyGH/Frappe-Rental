"""Contract signing API (T41) for the portal and staff app. Checks, then calls services.esign."""

import frappe
from frappe import _

from frappe_rental.services import esign


def _contract(name: str, staff: bool = False):
	if not name or not frappe.db.exists("Rental Contract", name):
		frappe.throw(_("Contract not found"), frappe.DoesNotExistError)
	doc = frappe.get_doc("Rental Contract", name)
	allowed = (
		frappe.has_permission("Rental Contract", "write", doc) if staff else esign.can_sign_for(doc.customer)
	)
	if not allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


@frappe.whitelist()
def terms(name: str) -> dict:
	doc = _contract(name)
	return {
		"name": doc.name,
		"status": doc.status,
		"html": doc.rendered_terms,
		"require_otp": doc.require_otp,
		"signed_on": doc.signed_on,
	}


@frappe.whitelist(methods=["POST"])
def request_signature(name: str) -> dict:
	doc = _contract(name, staff=True)
	esign.request_signature(doc)
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def request_otp(name: str) -> dict:
	esign.request_otp(_contract(name))
	return {"sent": True}


@frappe.whitelist(methods=["POST"])
def sign(
	name: str, signer_name: str, signature: str, signature_type: str = "Typed", otp: str | None = None
) -> dict:
	doc = _contract(name)
	esign.customer_sign(doc, signer_name, signature, signature_type, otp)
	return {"signed_on": doc.signed_on}


@frappe.whitelist(methods=["POST"])
def countersign(name: str) -> dict:
	doc = _contract(name, staff=True)
	esign.countersign(doc)
	return {"status": doc.status, "signed_pdf": doc.signed_pdf}


# Maintenance visits (T46)


@frappe.whitelist(methods=["POST"])
def request_service(name: str, notes: str) -> dict:
	"""Customer (portal) or staff asks for an unplanned visit."""
	doc = _contract(name)
	if not frappe.has_permission("Rental Contract", "write", doc):
		doc.flags.ignore_permissions = (
			True  # a customer who may sign for it (checked by _contract) asks for a visit
		)
	from frappe_rental.services import visits

	return {"visit": visits.request_service(doc, notes)}


@frappe.whitelist(methods=["POST"])
def assign_visit(name: str, visit: str, technician: str, start: str, hours: float = 2) -> dict:
	doc = _contract(name, staff=True)
	from frappe_rental.services import visits

	return {"booking": visits.assign(doc, visit, technician, start, float(hours or 2))}


@frappe.whitelist(methods=["POST"])
def complete_visit(name: str, visit: str, notes: str | None = None) -> dict:
	doc = _contract(name, staff=True)
	from frappe_rental.services import visits

	visits.complete(doc, visit, notes)
	return {"status": "Done"}


# Screens (T47)


@frappe.whitelist(methods=["GET", "POST"])
def listing(
	status: str | None = None, search: str | None = None, start: int = 0, page_length: int = 20
) -> dict:
	from frappe_rental.services import contract_views

	return contract_views.listing(status or None, search or None, start, page_length)


@frappe.whitelist(methods=["GET", "POST"])
def detail(name: str) -> dict:
	from frappe_rental.services import contract_views

	return contract_views.detail(name)


def _signed_in() -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to see your contracts"), frappe.PermissionError)


@frappe.whitelist(methods=["GET", "POST"])
def my_contracts() -> dict:
	from frappe_rental.services import contract_views

	_signed_in()
	return contract_views.my_listing()


@frappe.whitelist(methods=["GET", "POST"])
def my_contract(name: str) -> dict:
	from frappe_rental.services import contract_views

	_signed_in()
	return contract_views.my_detail(name)
