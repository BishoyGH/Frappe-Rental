"""Native onboarding: fixtures are imported and completion follows the data."""

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.api import alerts as api
from frappe_rental.services import onboarding


class TestOnboarding(FrappeTestCase):
	def test_module_onboarding_synced(self):
		self.assertTrue(frappe.db.exists("Module Onboarding", "Rental"))
		titles = frappe.get_all("Onboarding Step Map", filters={"parent": "Rental"}, pluck="step")
		self.assertEqual(len(titles), 7)
		for t in titles:
			self.assertEqual(frappe.db.get_value("Onboarding Step", t, "action"), "Create Entry")

	def test_workspace_shows_onboarding(self):
		content = frappe.db.get_value("Workspace", "Rental", "content")
		self.assertIn('"onboarding_name": "Rental"', content)

	def test_insert_completes_step_and_sync_is_idempotent(self):
		frappe.db.set_value("Onboarding Step", "Create a Rental Type", "is_complete", 0)
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": "Onb Type", "mode": "Resource", "time_unit": "Day"}
		).insert()
		self.assertEqual(frappe.db.get_value("Onboarding Step", "Create a Rental Type", "is_complete"), 1)
		onboarding.sync()
		onboarding.sync()
		self.assertEqual(frappe.db.get_value("Onboarding Step", "Create a Rental Type", "is_complete"), 1)

	def test_status_api(self):
		out = api.onboarding()
		self.assertEqual(out["total"], 7)
		self.assertEqual({s["doctype"] for s in out["steps"]} & {"Rental Booking"}, {"Rental Booking"})

	def test_status_needs_staff(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.onboarding()
		finally:
			frappe.set_user("Administrator")
