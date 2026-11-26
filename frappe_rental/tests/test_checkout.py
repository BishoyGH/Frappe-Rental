import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import checkout as svc
from frappe_rental.services.setup import create_defaults


def make(doctype, key, name, **kw):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, key: name, **kw}).insert()
	return name


class TestCheckout(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		cur = frappe.db.get_value("Company", company, "default_currency")
		if not frappe.db.exists("Rental Charge", {"charge_name": "T35 Helmet"}):
			frappe.get_doc(
				{"doctype": "Rental Charge", "charge_name": "T35 Helmet", "charge_type": "Fixed", "amount": 7}
			).insert()
		cls.helmet = frappe.db.get_value("Rental Charge", {"charge_name": "T35 Helmet"})
		make(
			"Rental Rate Card",
			"card_name",
			"T35 Card",
			currency=cur,
			rates=[{"time_unit": "Hour", "rate": 10}],
			charges=[{"charge": cls.helmet, "is_mandatory": 0}],
		)
		make("Rental Type", "type_name", "T35 Type", mode="Resource", time_unit="Hour", requires_hold=1)
		make("Rental Type", "type_name", "T35 Signed", mode="Resource", time_unit="Hour", requires_contract=1)
		if not frappe.db.exists("Rental Terms Template", {"rental_type": "T35 Signed"}):
			frappe.get_doc(
				{
					"doctype": "Rental Terms Template",
					"template_name": f"T35 {random_string(6)}",
					"rental_type": "T35 Signed",
					"is_active": 1,
					"body": "<p>Terms for {{ customer.customer_name }}</p>",
				}
			).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def item(self, rtype="T35 Type"):
		doc = frappe.get_doc(
			{
				"doctype": "Rental Item",
				"item_name": f"T35 {random_string(6)}",
				"rental_type": rtype,
				"rate_card": "T35 Card",
				"is_published": 1,
			}
		).insert()
		frappe.get_doc(
			{"doctype": "Rental Unit", "unit_name": f"T35 {random_string(6)}", "rental_item": doc.name}
		).insert()
		return doc.name

	def guest_start(self, item, email=None, **kw):
		frappe.set_user("Guest")
		return svc.start(
			{
				"item": item,
				"from_datetime": "2027-04-01 10:00",
				"to_datetime": "2027-04-01 12:00",
				"details": {
					"full_name": "Pat Guest",
					"email": email or f"t35-{random_string(8)}@example.com",
				},
				**kw,
			}
		)

	def test_guest_checkout_creates_account_and_confirms(self):
		item = self.item()
		self.assertEqual([e["label"] for e in svc.extras(item)], ["T35 Helmet"])
		out = self.guest_start(item, extras=[self.helmet])
		self.assertTrue(out["new_user"])
		self.assertNotEqual(frappe.session.user, "Guest")
		self.assertEqual(out["status"], "Hold")
		self.assertEqual(out["net_total"], 27)  # 2 hours at 10 plus the helmet
		customer = frappe.db.get_value("Rental Booking", out["name"], "customer")
		self.assertEqual(svc.my_customers(), [customer])
		done = svc.finish(out["name"])
		self.assertEqual((done["docstatus"], done["status"]), (1, "Confirmed"))

	def test_existing_email_must_sign_in(self):
		item = self.item()
		email = f"t35-{random_string(8)}@example.com"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Taken"}).insert()
		with self.assertRaises(svc.SignInRequired):
			self.guest_start(item, email=email.upper())

	def test_returning_customer_reuses_customer_and_others_cannot_see(self):
		item = self.item()
		first = self.guest_start(item)
		user = frappe.session.user
		customer = svc.my_customers()[0]
		frappe.set_user("Administrator")
		frappe.set_user(user)
		second = svc.start(
			{"item": item, "from_datetime": "2027-04-02 10:00", "to_datetime": "2027-04-02 11:00"}
		)
		self.assertFalse(second["new_user"])
		self.assertEqual(frappe.db.get_value("Rental Booking", second["name"], "customer"), customer)
		self.guest_start(
			item, from_datetime="2027-04-03 10:00", to_datetime="2027-04-03 11:00"
		)  # someone else
		with self.assertRaises(frappe.DoesNotExistError):
			svc.summary(first["name"])
		frappe.set_user("Guest")
		with self.assertRaises(frappe.DoesNotExistError):
			svc.finish(first["name"])

	def test_unknown_extra_and_unpublished_item_refused(self):
		item = self.item()
		with self.assertRaises(frappe.ValidationError):
			self.guest_start(item, extras=["Nope"])
		frappe.set_user("Administrator")
		frappe.db.set_value("Rental Item", item, "is_published", 0)
		with self.assertRaises(frappe.DoesNotExistError):
			self.guest_start(item)

	def test_contract_is_signed_in_the_flow(self):
		item = self.item("T35 Signed")
		out = self.guest_start(item)
		self.assertTrue(out["needs_signature"])
		self.assertIn("Pat Guest", out["contract"]["html"])
		with self.assertRaises(frappe.ValidationError):
			svc.finish(out["name"])
		signed = svc.sign(out["name"], "Pat Guest", "Pat Guest")
		self.assertFalse(signed["needs_signature"])
		self.assertEqual(svc.finish(out["name"])["status"], "Confirmed")
