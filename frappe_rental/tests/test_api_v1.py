"""Contract tests for the REST v1 endpoints (T33): shape of each answer and its permission failure."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import booking as booking_api
from frappe_rental.api import payment as payment_api
from frappe_rental.api import pricing as pricing_api
from frappe_rental.services import demo, erpnext_sync, idempotency
from frappe_rental.tests.test_staff_app import make_user


class TestApiV1(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()
		cls.item = cls.data["items"]["Device"]
		cls.customer = cls.data["customers"][0]
		cls.agent = make_user("Rental Agent")
		cls.accountant = make_user("Rental Accountant")

	def tearDown(self):
		frappe.set_user("Administrator")

	def booking(self, day, confirm=True):
		return demo.book(
			self.customer,
			"Device",
			self.item,
			f"2030-01-{day:02d} 10:00",
			f"2030-01-{day + 2:02d} 10:00",
			confirm,
		)

	def payload(self, day):
		return {
			"customer": self.customer,
			"rental_type": "Device",
			"location": demo.LOCATION,
			"from_datetime": f"2030-02-{day:02d} 10:00",
			"to_datetime": f"2030-02-{day + 2:02d} 10:00",
			"lines": [{"rental_item": self.item}],
		}

	def test_pricing_quote(self):
		out = pricing_api.quote([{"rental_item": self.item}], "2030-03-01 10:00", "2030-03-03 10:00")
		self.assertGreater(out["grand_total"], 0)
		self.assertEqual(out["lines"][0]["rental_item"], self.item)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			pricing_api.quote([{"rental_item": self.item}], "2030-03-01 10:00", "2030-03-03 10:00")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			pricing_api.quote([], "2030-03-01 10:00", "2030-03-03 10:00")

	def test_create_is_idempotent(self):
		key = random_string(10)
		first = booking_api.create(self.payload(1), hold=1, idempotency_key=key)
		again = booking_api.create(self.payload(1), hold=1, idempotency_key=key)
		self.assertEqual(first["name"], again["name"])
		self.assertEqual(first["status"], "Hold")
		with self.assertRaises(idempotency.IdempotencyConflict):
			booking_api.create(self.payload(5), hold=1, idempotency_key=key)
		other = booking_api.create(self.payload(9), idempotency_key=random_string(10))
		self.assertNotEqual(other["name"], first["name"])
		frappe.set_user(self.accountant)
		with self.assertRaises(frappe.PermissionError):
			booking_api.create(self.payload(13))

	def test_get_modify_cancel_preview(self):
		held = booking_api.create(self.payload(15), hold=1)["name"]
		self.assertEqual(booking_api.get(held)["name"], held)
		moved = booking_api.modify(held, "2030-02-16 10:00", "2030-02-18 10:00")
		self.assertEqual(str(moved["from_datetime"]), "2030-02-16 10:00:00")
		name = self.booking(3)
		preview = booking_api.cancel(name, preview=1)
		self.assertIn("refund", str(preview).lower())
		self.assertEqual(frappe.db.get_value("Rental Booking", name, "docstatus"), 1)
		frappe.set_user(self.accountant)
		with self.assertRaises(frappe.PermissionError):
			booking_api.modify(held, "2030-02-20 10:00", "2030-02-22 10:00")
		with self.assertRaises(frappe.PermissionError):
			booking_api.cancel(name)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			booking_api.get(held)

	def test_checkout_and_checkin(self):
		name = self.booking(7)
		out = booking_api.checkout(name)
		self.assertEqual(out["handover_type"], "Check-out")
		back = booking_api.checkin(name)
		self.assertEqual(back["handover_type"], "Return")
		frappe.set_user(self.accountant)
		with self.assertRaises(frappe.PermissionError):
			booking_api.checkout(self.booking_as_admin(11))

	def booking_as_admin(self, day):
		user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			return self.booking(day)
		finally:
			frappe.set_user(user)

	def test_list_mine(self):
		user = make_user("Customer")
		cust = frappe.get_doc("Customer", self.customer)
		cust.append("portal_users", {"user": user})
		cust.save()
		name = self.booking(19)
		stranger = make_user("Customer")
		frappe.set_user(user)
		rows = booking_api.list_mine()["rows"]
		self.assertIn(name, [r["name"] for r in rows])
		frappe.set_user(stranger)
		self.assertEqual(booking_api.list_mine()["rows"], [])
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			booking_api.list_mine()

	def test_payment_request(self):
		name = self.booking(23)
		with self.assertRaises(frappe.ValidationError):
			payment_api.create_request(name)  # no invoice yet
		erpnext_sync.make_sales_invoice(frappe.get_doc("Rental Booking", name), submit=True)
		pr = payment_api.create_request(name)
		self.assertTrue(frappe.db.exists("Payment Request", pr["name"]))
		self.assertEqual(payment_api.create_request(name)["name"], pr["name"])
		frappe.set_user(self.agent)
		with self.assertRaises(frappe.PermissionError):
			payment_api.create_request(name)
