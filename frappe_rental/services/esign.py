"""E-signature (T41): customer signs on the portal (typed or drawn, optional OTP), staff countersign.

- `request_signature` renders the snapshot (T40 `send_for_signature`) and emits
  `contract_signature_requested`; Notifications or the portal page take it from there.
- `request_otp` emails a 6-digit code; only its salted hash and expiry are stored (10 minutes).
- `customer_sign` checks the signer may sign for the customer, the code when required, and records
  the audit fields (type, signature, IP, browser, time). The contract stays Awaiting Signature.
- `countersign` by an internal user activates the contract (T40 `activate`), stores a signed PDF of
  the snapshot and audit trail, and emits `contract_signed`. After that the contract is immutable
  except by amendment (T40), and signature fields can never change.
- `remind_unsigned` (daily) emits `contract_signature_reminder` every 3 days while unsigned.
"""

import hashlib
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, date_diff, get_datetime, getdate, now_datetime, nowdate

from frappe_rental.services import contracts, events

OTP_MINUTES = 10
REMIND_EVERY_DAYS = 3


def request_signature(doc) -> None:
	contracts.send_for_signature(doc)
	events.emit("contract_signature_requested", doc)


def _hash(contract: str, code: str) -> str:
	return hashlib.sha256(f"{contract}:{code}:{frappe.local.site}".encode()).hexdigest()


def _new_code() -> str:
	return f"{secrets.randbelow(10**6):06d}"


def request_otp(doc) -> None:
	if doc.status != "Awaiting Signature":
		frappe.throw(_("This contract is not waiting for a signature"))
	code = _new_code()
	doc.db_set(
		{
			"otp_hash": _hash(doc.name, code),
			"otp_expires_on": add_to_date(now_datetime(), minutes=OTP_MINUTES),
		}
	)
	email = frappe.db.get_value("Customer", doc.customer, "email_id")
	if email:
		frappe.sendmail(
			recipients=[email],
			subject=_("Your signing code for {0}").format(doc.name),
			message=_("Your code is {0}. It expires in {1} minutes.").format(code, OTP_MINUTES),
			now=False,
		)


def can_sign_for(customer: str, user: str | None = None) -> bool:
	"""Staff with write on contracts, or a portal user whose Contact links to the customer."""
	user = user or frappe.session.user
	if frappe.has_permission("Rental Contract", "write", user=user):
		return True
	contacts = frappe.get_all("Contact", filters={"user": user}, pluck="name")
	if not contacts:
		return False
	return bool(
		frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Contact",
				"parent": ["in", contacts],
				"link_doctype": "Customer",
				"link_name": customer,
			},
		)
	)


def customer_sign(
	doc,
	signer_name: str,
	signature: str,
	signature_type: str = "Typed",
	otp: str | None = None,
	ip=None,
	user_agent=None,
) -> None:
	if doc.status != "Awaiting Signature" or doc.signed_on:
		frappe.throw(_("This contract is not waiting for a signature"))
	if not can_sign_for(doc.customer):
		frappe.throw(_("You cannot sign for {0}").format(doc.customer), frappe.PermissionError)
	if signature_type not in ("Typed", "Drawn"):
		frappe.throw(_("Sign by typing your name or drawing"))
	if not (signer_name or "").strip() or not (signature or "").strip():
		frappe.throw(_("Name and signature are required"))
	if signature_type == "Drawn" and not signature.startswith("data:image/"):
		frappe.throw(_("A drawn signature must be an image"))
	if doc.require_otp:
		if not doc.otp_hash or not otp or get_datetime(doc.otp_expires_on) < now_datetime():
			frappe.throw(_("Request a new signing code"))
		if not secrets.compare_digest(doc.otp_hash, _hash(doc.name, str(otp).strip())):
			frappe.throw(_("The signing code is wrong"))
	doc.db_set(
		{
			"signed_by": signer_name.strip(),
			"signed_on": now_datetime(),
			"signature_type": signature_type,
			"signature": signature,
			"signer_ip": ip or getattr(frappe.local, "request_ip", None),
			"signer_user_agent": user_agent or _user_agent(),
			"otp_hash": None,
			"otp_expires_on": None,
		}
	)


def _user_agent() -> str | None:
	request = getattr(frappe.local, "request", None)
	return request.headers.get("User-Agent") if request else None


def countersign(doc, user: str | None = None) -> str:
	user = user or frappe.session.user
	if not doc.signed_on:
		frappe.throw(_("The customer has not signed yet"))
	if not frappe.has_permission("Rental Contract", "write", doc, user=user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	contracts.activate(doc, doc.signed_by, countersigned_by=user)  # keeps the customer's signing time
	pdf = _signed_pdf(doc)
	if pdf:
		doc.db_set("signed_pdf", pdf)
	events.emit("contract_signed", doc)
	return doc.erpnext_contract


def audit_html(doc) -> str:
	esc = frappe.utils.escape_html
	signature = (
		f'<img src="{esc(doc.signature)}" style="max-height:80px">'
		if doc.signature_type == "Drawn"
		else f"<em>{esc(doc.signature or '')}</em>"
	)
	return (
		f"{doc.rendered_terms}<hr><h4>{_('Signatures')}</h4>"
		f"<p>{_('Customer')}: {esc(doc.signed_by or '')} {signature}<br>{_('Signed on')}: {doc.signed_on} "
		f"IP {esc(doc.signer_ip or '-')}</p>"
		f"<p>{_('Countersigned by')}: {esc(doc.countersigned_by or '')} {_('on')} {doc.countersigned_on}</p>"
	)


def _signed_pdf(doc) -> str | None:
	"""Attach a private PDF of the signed terms and audit trail. Returns the file URL."""
	from frappe.utils.pdf import get_pdf

	try:
		content = get_pdf(audit_html(doc))
	except Exception:
		frappe.log_error(title=_("Signed PDF failed for {0}").format(doc.name))
		return None
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}-signed.pdf",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": content,
		}
	)
	file.flags.ignore_permissions = True  # the signed copy of a permitted contract
	file.insert()
	return file.file_url


def remind_unsigned(today=None) -> int:
	today = getdate(today or nowdate())
	fired = 0
	for row in frappe.get_all(
		"Rental Contract",
		filters={"status": "Awaiting Signature", "signed_on": ["is", "not set"]},
		fields=["name", "modified"],
	):
		age = date_diff(today, getdate(row.modified))
		if age >= REMIND_EVERY_DAYS and age % REMIND_EVERY_DAYS == 0:
			if events.emit(
				"contract_signature_reminder", frappe.get_doc("Rental Contract", row.name), key=str(today)
			):
				fired += 1
	return fired
