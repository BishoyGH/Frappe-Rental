"""Contract screens (T47): staff tabs and the customer's own contracts."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import contract as api
from frappe_rental.services import contracts
from frappe_rental.tests.test_contracts import make_contract


def portal_user(customer: str) -> str:
	email = f"t47-{random_string(6)}@example.com"
	frappe.get_doc({"doctype": "User", "email": email, "first_name": "T47", "send_welcome_email": 0}).insert(
		ignore_permissions=True  # test fixture
	)
	frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": "T47",
			"user": email,
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		}
	).insert(ignore_permissions=True)  # test fixture
	return email


def active(**kw):
	doc = make_contract(**kw)
	contracts.send_for_signature(doc)
	contracts.activate(doc, "Jane Customer", countersigned_by="Administrator")
	return doc


class TestContractViews(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_staff_listing_and_tabs(self):
		doc = make_contract(sla_response_hours=4, visit_frequency="Quarterly")
		name = frappe.db.get_value("Customer", doc.customer, "customer_name")
		rows = api.listing(search=name)["rows"]
		self.assertEqual([r["name"] for r in rows], [doc.name])
		self.assertEqual(rows[0]["customer_name"], name)
		self.assertEqual(api.listing(status="Active", search=name)["rows"], [])
		d = api.detail(doc.name)
		self.assertEqual(d["status"], "Draft")
		self.assertTrue(d["actions"]["send_for_signature"])
		self.assertFalse(d["actions"]["countersign"])
		for tab in ("terms", "allocations", "billing", "visits", "amendments"):
			self.assertIn(tab, d)
		self.assertEqual(d["billing"]["bookings"], [])

	def test_customers_see_only_their_own_offered_contracts(self):
		mine, theirs = active(), active()
		draft = make_contract(customer=mine.customer)
		user, other = portal_user(mine.customer), portal_user(theirs.customer)
		frappe.set_user(user)
		self.assertEqual([r["name"] for r in api.my_contracts()["rows"]], [mine.name])  # not the draft
		detail = api.my_contract(mine.name)
		self.assertIn("Fee 300", detail["terms_html"])
		self.assertTrue(detail["can_request_service"])
		for name in (theirs.name, draft.name):
			with self.assertRaises(frappe.DoesNotExistError):
				api.my_contract(name)
		with self.assertRaises(frappe.PermissionError):
			api.listing()  # the staff list is not for customers
		with self.assertRaises(frappe.PermissionError):
			api.detail(mine.name)
		from frappe_rental.api import portal as portal_api

		with self.assertRaises(frappe.DoesNotExistError):
			portal_api.download_contract(mine.name)  # no signed PDF yet
		frappe.set_user(other)
		with self.assertRaises(frappe.DoesNotExistError):
			api.my_contract(mine.name)
		with self.assertRaises(frappe.DoesNotExistError):
			portal_api.download_contract(mine.name)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.my_contracts()

	def test_customer_requests_a_visit_and_signs(self):
		doc = active(sla_response_hours=4, sla_resolution_hours=24)
		user = portal_user(doc.customer)
		frappe.set_user(user)
		api.request_service(doc.name, "The printer jams")
		visits = api.my_contract(doc.name)["visits"]
		self.assertEqual([v["notes"] for v in visits], ["The printer jams"])
		frappe.set_user("Administrator")
		waiting = make_contract(customer=doc.customer)
		contracts.send_for_signature(waiting)
		frappe.set_user(user)
		self.assertTrue(api.my_contract(waiting.name)["awaiting_signature"])
		api.sign(waiting.name, "Jane Customer", "Jane Customer")
		self.assertFalse(api.my_contract(waiting.name)["awaiting_signature"])
		self.assertTrue(api.my_contract(waiting.name)["signed"])
