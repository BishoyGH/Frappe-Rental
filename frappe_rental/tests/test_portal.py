"""My bookings portal (T37): a customer sees and changes only their own bookings."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import booking as booking_api
from frappe_rental.api import portal as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import checkout, portal
from frappe_rental.services.setup import create_defaults


def make(doctype, key, name, **kw):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, key: name, **kw}).insert()
	return name


class TestPortal(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		cur = frappe.db.get_value("Company", company, "default_currency")
		make(
			"Rental Rate Card",
			"card_name",
			"T37 Card",
			currency=cur,
			rates=[{"time_unit": "Hour", "rate": 10}],
		)
		make("Rental Type", "type_name", "T37 Type", mode="Resource", time_unit="Hour", requires_hold=1)

	def tearDown(self):
		frappe.set_user("Administrator")

	def item(self):
		frappe.set_user("Administrator")  # a previous step may have left a customer signed in
		doc = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T37 {random_string(6)}",
				"rental_type": "T37 Type",
				"rate_card": "T37 Card",
				"is_published": 1,
			}
		).insert()
		for _n in range(2):
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"T37 {random_string(6)}", "rental_item": doc.name}
			).insert()
		return doc.name

	def customer_booking(self, item, day="2027-06-01", confirm=False):
		"""A new guest signs up and books. Returns (user, booking name); the session stays on that user."""
		frappe.set_user("Guest")
		out = checkout.start(
			{
				"item": item,
				"from_datetime": f"{day} 10:00",
				"to_datetime": f"{day} 12:00",
				"details": {"full_name": "Pat Portal", "email": f"t37-{random_string(8)}@example.com"},
			}
		)
		if confirm:
			checkout.finish(out["name"])
		return frappe.session.user, out["name"]

	def test_each_customer_sees_only_their_own(self):
		item = self.item()
		user_a, a = self.customer_booking(item, "2027-06-01")
		user_b, b = self.customer_booking(item, "2027-06-02")
		self.assertEqual([r["name"] for r in api.listing()["rows"]], [b])
		self.assertEqual(api.detail(b)["name"], b)
		for call in (
			lambda: api.detail(a),
			lambda: api.cancel_preview(a),
			lambda: api.cancel(a),
			lambda: api.change(a, "2027-06-05 10:00", "2027-06-05 12:00"),
			lambda: api.download(a, "invoice", "SINV-0001"),
			lambda: checkout.payment(a),
		):
			with self.assertRaises(frappe.DoesNotExistError):
				call()
		frappe.set_user(user_a)
		self.assertEqual([r["name"] for r in api.listing()["rows"]], [a])
		self.assertEqual(frappe.db.get_value("Rental Booking", a, "status"), "Hold")

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		for call in (api.listing, lambda: api.detail("X"), lambda: api.cancel("X")):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_change_a_held_booking(self):
		_user, name = self.customer_booking(self.item(), "2027-06-10")
		before = api.detail(name)
		out = api.change(name, "2027-06-10 10:00", "2027-06-10 14:00")
		self.assertEqual(out["net_total"], 40)
		self.assertGreater(out["net_total"], before["net_total"])
		self.assertTrue(out["can_change"])

	def test_cancel_held_and_confirmed(self):
		_user, held = self.customer_booking(self.item(), "2027-06-20")
		self.assertTrue(api.cancel_preview(held)["held"])
		self.assertEqual(api.cancel(held)["status"], "Cancelled")
		with self.assertRaises(frappe.ValidationError):
			api.cancel(held)  # nothing left to cancel
		_user, confirmed = self.customer_booking(self.item(), "2027-06-21", confirm=True)
		detail = api.detail(confirmed)
		self.assertEqual(detail["status"], "Confirmed")
		self.assertFalse(detail["can_change"])
		self.assertTrue(detail["can_cancel"])
		preview = api.cancel_preview(confirmed)
		self.assertIn("refund", preview)
		out = api.cancel(confirmed)
		self.assertEqual(out["status"], "Cancelled")
		self.assertEqual(out["cancellation"]["refund"], preview["refund"])

	def test_invoices_and_documents_are_the_bookings_own(self):
		item = self.item()
		_user, name = self.customer_booking(item, "2027-07-01", confirm=True)
		frappe.set_user("Administrator")
		invoice = booking_api.make_invoice(name)["sales_invoice"]
		other_user, other = self.customer_booking(item, "2027-07-02", confirm=True)
		frappe.set_user(other_user)
		self.assertEqual(api.detail(other)["invoices"], [])
		with self.assertRaises(frappe.DoesNotExistError):
			api.download(other, "invoice", invoice)  # an invoice of someone else's booking
		with self.assertRaises(frappe.DoesNotExistError):
			api.download(other, "contract", "RCON-0001")
		frappe.set_user(_user)
		detail = api.detail(name)
		self.assertEqual([i["name"] for i in detail["invoices"]], [invoice])
		self.assertEqual(detail["documents"][0], {"kind": "invoice", "ref": invoice, "label": invoice})
		self.assertEqual(detail["balance_due"], detail["invoices"][0]["outstanding_amount"])
		try:
			portal.download(name, "invoice", invoice)
		except Exception as e:  # wkhtmltopdf may be missing on a bare bench
			self.assertNotIsInstance(e, (frappe.PermissionError, frappe.DoesNotExistError))
		else:
			self.assertEqual(frappe.local.response.type, "pdf")
