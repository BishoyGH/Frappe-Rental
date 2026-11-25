import time

from frappe.tests.utils import FrappeTestCase

from frappe_rental.tests.utils import make_company, make_customer, make_fixture_set, make_item


class TestHarness(FrappeTestCase):
	def test_fixture_set_is_fast_and_idempotent(self):
		start = time.monotonic()
		fx = make_fixture_set()
		self.assertLess(time.monotonic() - start, 5)
		for doctype, key in (("Company", "company"), ("Customer", "customer"), ("Item", "item")):
			self.assertTrue(frappe_exists(doctype, fx[key]))
		# idempotent
		self.assertEqual(make_company(), fx["company"])
		self.assertEqual(make_item(fx["item"]), fx["item"])
		self.assertEqual(make_customer(fx["customer"]), fx["customer"])


def frappe_exists(doctype, name):
	import frappe

	return bool(frappe.db.exists(doctype, name))
