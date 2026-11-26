"""Online payments (T36): Stripe sessions, signed webhooks, replay safety, failure and retry."""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, random_string

from frappe_rental.api import booking as booking_api
from frappe_rental.services import payments
from frappe_rental.tests import test_erpnext_sync as t16

SECRET = "whsec_test_t36"


class FakeStripe(payments.StripeAdapter):
	calls = []

	def _post(self, path, data):
		FakeStripe.calls.append((path, data))
		sid = f"cs_test_{random_string(10)}"
		return {"id": sid, "url": f"https://checkout.stripe.test/{sid}"}


def signed(event: dict, secret=SECRET, stamp=None):
	payload = json.dumps(event).encode()
	stamp = stamp or int(time.time())
	sig = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
	return payload, {"Stripe-Signature": f"t={stamp},v1={sig}"}


def event(kind, session_id, status="paid"):
	return {
		"id": f"evt_{random_string(10)}",
		"type": kind,
		"data": {"object": {"id": session_id, "payment_status": status}},
	}


class TestPayments(FrappeTestCase):
	_tax_template = t16.TestErpnextSync.__dict__["_tax_template"]
	make_fixtures = t16.TestErpnextSync.__dict__["make_fixtures"]
	booking = t16.TestErpnextSync.booking

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_fixtures()
		if not frappe.db.exists("Rental Deposit Rule", "T36 Fixed"):
			frappe.get_doc(
				{
					"doctype": "Rental Deposit Rule",
					"rule_name": "T36 Fixed",
					"deposit_type": "Fixed",
					"amount": 200,
					"refundable": 1,
				}
			).insert()
		frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", "T36 Fixed")
		settings = frappe.get_single("Rental Settings")
		settings.payment_provider = "Stripe"
		settings.payment_account = frappe.get_cached_value("Company", cls.company, "default_cash_account")
		settings.stripe_secret_key = "sk_test_t36"
		settings.stripe_webhook_secret = SECRET
		settings.save()
		cls.patcher = patch.dict(payments.PROVIDERS, {"Stripe": FakeStripe})
		cls.patcher.start()

	@classmethod
	def tearDownClass(cls):
		cls.patcher.stop()
		frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", None)
		frappe.db.set_single_value("Rental Settings", "payment_provider", None)
		super().tearDownClass()

	def held(self):
		return self.booking(taxes=False, submit=False)

	def pay(self, doc, purpose="Deposit"):
		return payments.start(doc, purpose, "https://x.test/ok", "https://x.test/cancel")

	def deliver(self, kind, session_id, status="paid", **kw):
		payload, headers = signed(event(kind, session_id, status), **kw)
		return payments.handle_webhook("Stripe", payload, headers)

	def test_deposit_paid_once_even_when_replayed(self):
		doc = self.held()
		self.assertEqual(flt(doc.deposit_required), 200)
		out = self.pay(doc)
		self.assertIn("checkout.stripe.test", out["payment_url"])
		path, data = FakeStripe.calls[-1]
		self.assertEqual(path, "/checkout/sessions")
		self.assertEqual(data["line_items[0][price_data][unit_amount]"], 20000)
		self.assertEqual(self.pay(doc)["payment"], out["payment"])  # open attempt is reused
		session = frappe.db.get_value("Rental Payment", out["payment"], "session_id")
		payload, headers = signed(event("checkout.session.completed", session))
		self.assertEqual(payments.handle_webhook("Stripe", payload, headers)["status"], "Paid")
		self.assertEqual(payments.handle_webhook("Stripe", payload, headers)["status"], "Paid")  # replay
		deposit = frappe.db.get_value("Rental Deposit", {"rental_booking": doc.name})
		self.assertEqual(flt(frappe.db.get_value("Rental Deposit", deposit, "amount_received")), 200)
		self.assertEqual(frappe.db.count("Journal Entry", {"rental_deposit": deposit, "docstatus": 1}), 1)
		self.assertEqual(flt(frappe.db.get_value("Rental Booking", doc.name, "deposit_paid")), 200)
		with self.assertRaises(frappe.ValidationError):
			self.pay(frappe.get_doc("Rental Booking", doc.name))  # nothing due any more

	def test_bad_or_stale_signature_is_refused(self):
		doc = self.held()
		session = frappe.db.get_value("Rental Payment", self.pay(doc)["payment"], "session_id")
		with self.assertRaises(payments.WebhookError):
			self.deliver("checkout.session.completed", session, secret="whsec_wrong")
		with self.assertRaises(payments.WebhookError):
			self.deliver("checkout.session.completed", session, stamp=int(time.time()) - 3600)
		self.assertEqual(frappe.db.get_value("Rental Payment", {"session_id": session}, "status"), "Pending")
		self.assertFalse(self.deliver("checkout.session.completed", "cs_unknown")["handled"])
		self.assertFalse(self.deliver("customer.created", session)["handled"])

	def test_failure_then_retry(self):
		doc = self.held()
		first = self.pay(doc)
		session = frappe.db.get_value("Rental Payment", first["payment"], "session_id")
		self.assertEqual(self.deliver("checkout.session.async_payment_failed", session)["status"], "Failed")
		second = self.pay(doc)
		self.assertNotEqual(second["payment"], first["payment"])
		session2 = frappe.db.get_value("Rental Payment", second["payment"], "session_id")
		self.assertEqual(self.deliver("checkout.session.expired", session2)["status"], "Expired")
		third = self.pay(doc)
		session3 = frappe.db.get_value("Rental Payment", third["payment"], "session_id")
		self.assertEqual(self.deliver("checkout.session.completed", session3)["status"], "Paid")
		self.assertEqual(frappe.db.count("Rental Payment", {"rental_booking": doc.name, "status": "Paid"}), 1)

	def test_balance_payment_settles_invoice(self):
		frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", None)
		try:
			doc = self.booking(taxes=False)
			invoice = booking_api.make_invoice(doc.name)["sales_invoice"]
			doc.reload()
			out = self.pay(doc, "Balance")
			payment = frappe.get_doc("Rental Payment", out["payment"])
			self.assertEqual(payment.sales_invoice, invoice)
			self.deliver("checkout.session.completed", payment.session_id)
			self.deliver("checkout.session.completed", payment.session_id)  # replay
			self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount")), 0)
			self.assertEqual(
				frappe.db.count("Payment Entry Reference", {"reference_name": invoice, "docstatus": 1}), 1
			)
		finally:
			frappe.db.set_value("Rental Type", "T16 Device", "deposit_rule", "T36 Fixed")
