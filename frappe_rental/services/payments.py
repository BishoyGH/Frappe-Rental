"""Online payments (T36): deposits and balances through a payment provider, with a webhook.

A payment is one Rental Payment row per attempt: ``start`` asks the provider for a hosted checkout page and
stores its session id; the provider's webhook then marks the row Paid (posting the deposit Journal Entry or
the invoice Payment Entry) or Failed/Expired. The customer retries by starting again, which makes a new row;
an open Pending row is reused instead of opening a second session.

Replay safety: a webhook for a row that is already Paid changes nothing, and the row is locked while it is
settled, so two deliveries of the same event post once. Unknown sessions are ignored (200), so the provider
stops retrying events that are not ours.

Providers are adapters with ``create_session(payment, success_url, cancel_url)`` and
``parse_webhook(payload, headers)``. Stripe ships here; others register in ``PROVIDERS``.

Card-gateway apps that complete an ERPNext Payment Request (``api.payment.create_request``) keep working
alongside this; that path is ERPNext's own and behaves the same on v15 and v16.
"""

import hashlib
import hmac
import json
import time

import frappe
import requests
from frappe import _
from frappe.utils import flt, get_url, now_datetime

from frappe_rental.compat import erpnext as compat
from frappe_rental.services import deposits

DOCTYPE = "Rental Payment"
TOLERANCE = 300  # seconds a webhook signature stays valid


class WebhookError(frappe.ValidationError):
	http_status_code = 400


class StripeAdapter:
	name = "Stripe"
	API = "https://api.stripe.com/v1"

	def _secret(self, field: str) -> str:
		value = frappe.utils.password.get_decrypted_password(
			"Rental Settings", "Rental Settings", field, raise_exception=False
		)
		if not value:
			frappe.throw(_("Stripe is not configured in Rental Settings"))
		return value

	def _post(self, path: str, data: dict) -> dict:
		"""One Stripe API call. Tests replace this method."""
		res = requests.post(
			f"{self.API}{path}", data=data, auth=(self._secret("stripe_secret_key"), ""), timeout=20
		)
		body = res.json()
		if res.status_code >= 400:
			frappe.throw(
				_("Payment provider error: {0}").format(body.get("error", {}).get("message", res.status_code))
			)
		return body

	def create_session(self, payment, success_url: str, cancel_url: str) -> dict:
		precision = 2
		amount = int(round(flt(payment.amount, precision) * 100))  # Stripe takes minor units
		body = self._post(
			"/checkout/sessions",
			{
				"mode": "payment",
				"success_url": success_url,
				"cancel_url": cancel_url,
				"client_reference_id": payment.name,
				"metadata[rental_payment]": payment.name,
				"metadata[rental_booking]": payment.rental_booking,
				"line_items[0][quantity]": 1,
				"line_items[0][price_data][currency]": payment.currency.lower(),
				"line_items[0][price_data][unit_amount]": amount,
				"line_items[0][price_data][product_data][name]": _("{0} for booking {1}").format(
					_(payment.purpose), payment.rental_booking
				),
			},
		)
		return {"session_id": body["id"], "url": body["url"]}

	def verify(self, payload: bytes, header: str | None, now: float | None = None) -> None:
		parts = dict(p.split("=", 1) for p in (header or "").split(",") if "=" in p)
		stamp, signature = parts.get("t"), parts.get("v1")
		if not stamp or not signature:
			raise WebhookError(_("Missing webhook signature"))
		if abs((now or time.time()) - int(stamp)) > TOLERANCE:
			raise WebhookError(_("Webhook signature is too old"))
		secret = self._secret("stripe_webhook_secret").encode()
		expected = hmac.new(secret, f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
		if not hmac.compare_digest(expected, signature):
			raise WebhookError(_("Invalid webhook signature"))

	def parse_webhook(self, payload: bytes, headers) -> dict | None:
		"""Verified event as {event_id, session_id, outcome: paid|failed|expired}; None for other events."""
		self.verify(payload, headers.get("Stripe-Signature"))
		event = json.loads(payload)
		obj = (event.get("data") or {}).get("object") or {}
		outcome = {
			"checkout.session.completed": "paid" if obj.get("payment_status") == "paid" else None,
			"checkout.session.async_payment_succeeded": "paid",
			"checkout.session.async_payment_failed": "failed",
			"checkout.session.expired": "expired",
		}.get(event.get("type"))
		if not outcome:
			return None
		return {"event_id": event.get("id"), "session_id": obj.get("id"), "outcome": outcome}


PROVIDERS = {"Stripe": StripeAdapter}


def adapter(name: str | None = None):
	name = name or frappe.db.get_single_value("Rental Settings", "payment_provider")
	cls = PROVIDERS.get(name or "")
	return cls() if cls else None


def amount_due(booking, purpose: str) -> tuple[float, str | None]:
	if purpose == "Deposit":
		return flt(booking.deposit_required) - flt(booking.deposit_paid), None
	invoice = booking.get("sales_invoice")
	if not invoice or frappe.db.get_value("Sales Invoice", invoice, "docstatus") != 1:
		return 0, None
	return flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount")), invoice


def start(booking, purpose: str, success_url: str, cancel_url: str) -> dict:
	"""A hosted payment page for what the booking owes now. Reuses an open attempt."""
	if purpose not in ("Deposit", "Balance"):
		frappe.throw(_("Unknown payment purpose"))
	provider = adapter()
	if not provider:
		frappe.throw(_("Online payment is not set up. Contact us to pay."))
	amount, invoice = amount_due(booking, purpose)
	if amount <= 0:
		frappe.throw(_("Nothing is due for this booking"))
	open_row = frappe.db.get_value(
		DOCTYPE,
		{"rental_booking": booking.name, "purpose": purpose, "status": "Pending", "amount": amount},
		["name", "payment_url"],
		as_dict=True,
	)
	if open_row and open_row.payment_url:
		return {"payment": open_row.name, "payment_url": open_row.payment_url}
	payment = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"rental_booking": booking.name,
			"purpose": purpose,
			"amount": amount,
			"currency": booking.currency,
			"sales_invoice": invoice,
			"provider": provider.name,
		}
	)
	payment.flags.ignore_permissions = True  # the caller checked the booking belongs to the customer
	payment.insert()
	session = provider.create_session(payment, success_url, cancel_url)
	payment.db_set({"session_id": session["session_id"], "payment_url": session["url"]})
	return {"payment": payment.name, "payment_url": session["url"]}


def handle_webhook(provider_name: str, payload: bytes, headers) -> dict:
	provider = adapter(provider_name)
	if not provider:
		raise WebhookError(_("Unknown payment provider"))
	event = provider.parse_webhook(payload, headers)
	if not event:
		return {"handled": False}
	name = frappe.db.get_value(DOCTYPE, {"session_id": event["session_id"], "provider": provider.name})
	if not name:
		return {"handled": False}
	return {"handled": True, "status": settle(name, event["outcome"], event.get("event_id"))}


def settle(name: str, outcome: str, event_id: str | None = None) -> str:
	"""Apply a provider outcome to a payment once. Returns the payment's status."""
	frappe.db.sql(f"select name from `tab{DOCTYPE}` where name = %s for update", name)
	payment = frappe.get_doc(DOCTYPE, name)
	if payment.status == "Paid":
		return "Paid"  # replayed or late event: already posted
	if outcome != "paid":
		payment.db_set({"status": "Failed" if outcome == "failed" else "Expired", "provider_event": event_id})
		return payment.status
	account = frappe.db.get_single_value("Rental Settings", "payment_account")
	booking = frappe.get_doc("Rental Booking", payment.rental_booking)
	if payment.purpose == "Deposit":
		deposit = frappe.db.get_value("Rental Deposit", {"rental_booking": booking.name}) or deposits.request(
			booking
		)
		voucher_type = "Journal Entry"
		voucher = deposits.collect(
			deposit, payment.amount, cash_account=account, reference=payment.session_id
		)
	else:
		if not account:
			frappe.throw(_("Set the payment clearing account in Rental Settings"))
		voucher_type = "Payment Entry"
		voucher = compat.make_invoice_payment(
			payment.sales_invoice, payment.amount, account, payment.session_id
		)
	payment.db_set(
		{
			"status": "Paid",
			"paid_on": now_datetime(),
			"provider_event": event_id,
			"voucher_type": voucher_type,
			"voucher": voucher,
		}
	)
	return "Paid"


def urls(booking_name: str, item: str | None = None) -> tuple[str, str]:
	base = get_url("/rental/book")
	query = f"booking={booking_name}" + (f"&item={item}" if item else "")
	return f"{base}?{query}&paid=1", f"{base}?{query}&cancelled=1"
