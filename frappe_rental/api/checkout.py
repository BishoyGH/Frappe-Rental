"""Customer booking flow endpoints (T35). Guests may start; later steps need the booking's own customer.

Checks live in ``services.checkout``: ``own_booking`` scopes every booking call to the session user's
customers, and guest sign-up refuses an email that already has an account.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from frappe_rental.services import checkout
from frappe_rental.services.idempotency import idempotent

START_LIMIT = 10  # bookings started per IP per minute


def _obj(value, label):
	if isinstance(value, str):
		try:
			value = json.loads(value or "{}")
		except ValueError:
			frappe.throw(_("{0} must be JSON").format(label))
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be an object").format(label))
	return value


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def extras(item: str) -> list[dict]:
	return checkout.extras(item)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=START_LIMIT, seconds=60)
@idempotent
def start(booking: str | dict, idempotency_key: str | None = None) -> dict:
	data = _obj(booking, _("Booking"))
	if isinstance(data.get("extras"), str):
		data["extras"] = [data["extras"]]
	if not isinstance(data.get("extras") or [], list):
		frappe.throw(_("Extras must be a list"))
	return checkout.start(data)


@frappe.whitelist(methods=["GET", "POST"])
def summary(name: str) -> dict:
	return checkout.summary(name)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def sign(name: str, signer_name: str, signature: str, otp: str | None = None) -> dict:
	return checkout.sign(name, signer_name, signature, otp)


@frappe.whitelist(methods=["POST"])
def finish(name: str) -> dict:
	return checkout.finish(name)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def pay(name: str, purpose: str = "Deposit") -> dict:
	"""Where to pay the customer's own booking: the deposit while held, the balance once invoiced."""
	return checkout.payment(name, purpose)
