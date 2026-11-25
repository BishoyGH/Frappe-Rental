import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import setup
from frappe_rental.tests.utils import make_company


class TestInstallDefaults(FrappeTestCase):
	def setUp(self):
		make_company()

	def _snapshot(self):
		return {
			"roles": frappe.db.count("Role", {"name": ["in", list(setup.ROLES)]}),
			"item_group": frappe.db.count("Item Group", {"name": setup.ITEM_GROUP}),
			"accounts": frappe.db.count(
				"Account", {"account_name": ["in", [a for a, _ in setup.ACCOUNTS.values()]]}
			),
			"warehouses": frappe.db.count("Warehouse", {"warehouse_name": setup.WAREHOUSE}),
		}

	def test_creates_all_defaults(self):
		setup.create_defaults()
		snap = self._snapshot()
		self.assertEqual(snap["roles"], 6)
		self.assertEqual(snap["item_group"], 1)
		self.assertEqual(snap["accounts"], 5)
		self.assertEqual(snap["warehouses"], 1)
		settings = frappe.get_single("Rental Settings")
		for field in (*setup.ACCOUNTS, "rented_out_warehouse", "default_company"):
			self.assertTrue(settings.get(field), field)
		self.assertEqual(settings.hold_expiry_minutes, 15)

	def test_idempotent(self):
		setup.create_defaults()
		first = self._snapshot()
		setup.create_defaults()
		self.assertEqual(self._snapshot(), first)

	def test_does_not_overwrite_user_settings(self):
		setup.create_defaults()
		settings = frappe.get_single("Rental Settings")
		settings.hold_expiry_minutes = 30
		settings.save()
		setup.create_defaults()
		self.assertEqual(frappe.get_single("Rental Settings").hold_expiry_minutes, 30)
