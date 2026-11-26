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
