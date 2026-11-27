"""Full demo (T59): every preset gets an item, units where possible, and a maintenance contract."""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.services import demo


class TestFullDemo(FrappeTestCase):
	def test_every_preset_and_idempotent(self):
		out = demo.make_full_demo()
		presets = json.load(
			open(os.path.join(os.path.dirname(demo.__file__), "..", "rental", "presets", "types.json"))
		)
		names = [p["type_name"] for p in (presets if isinstance(presets, list) else presets["types"])]
		for name in names:
			self.assertIn(name, out["items"], name)
		self.assertEqual(
			frappe.db.get_value("Rental Unit", out["units"]["Photographer"], "unit_type"), "Provider"
		)
		self.assertEqual(
			frappe.db.get_value("Rental Unit", out["units"]["Bicycle"], "quantity_available"), 12
		)
		self.assertTrue(frappe.db.get_value("Rental Unit", out["units"]["Tool"], "batch_no"))
		contract = frappe.get_doc("Rental Contract", out["contract"])
		self.assertEqual((contract.status, len(contract.visits)), ("Active", 4))

		counts = (
			frappe.db.count("Rental Item"),
			frappe.db.count("Rental Unit"),
			frappe.db.count("Rental Contract"),
		)
		again = demo.make_full_demo()
		self.assertEqual(again["contract"], out["contract"])
		self.assertEqual(
			counts,
			(
				frappe.db.count("Rental Item"),
				frappe.db.count("Rental Unit"),
				frappe.db.count("Rental Contract"),
			),
		)
