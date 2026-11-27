import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import setup as api
from frappe_rental.services import demo, importer, rental_type
from frappe_rental.tests.test_staff_app import make_user


class TestImporter(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.data = demo.make_demo()
		cls.tag = random_string(5)

	def tearDown(self):
		frappe.set_user("Administrator")

	def items_csv(self):
		return (
			"item_name,rental_type,location,rate_card,bedrooms\n"
			f"Imp flat A {self.tag},Apartment,{demo.LOCATION},Demo Apartment Monthly,2\n"
			f"Imp flat B {self.tag},Apartment,{demo.LOCATION},Demo Apartment Monthly,3\n"
		)

	def test_items_then_units_with_identifiers_idempotent(self):
		out = importer.import_csv("Rental Item", self.items_csv())
		self.assertEqual(len(out["created"]), 2, out)
		self.assertEqual(frappe.db.get_value("Rental Item", out["created"][1], "bedrooms"), 3)
		again = importer.import_csv("Rental Item", self.items_csv())
		self.assertEqual((len(again["created"]), len(again["unchanged"])), (0, 2))

		units = (
			"unit_name,rental_item,barcode,id:rfid\n"
			f"Imp A1,Imp flat A {self.tag},BC-{self.tag}-1,RF-{self.tag}-1\n"
			f"Imp B1,Imp flat B {self.tag},BC-{self.tag}-2,RF-{self.tag}-2\n"
		)
		out = importer.import_csv("Rental Unit", units)
		self.assertEqual(len(out["created"]), 2, out)
		unit = frappe.get_doc("Rental Unit", out["created"][0])
		self.assertEqual([(r.id_type, r.id_value) for r in unit.external_ids], [("rfid", f"RF-{self.tag}-1")])
		# Matched by barcode: the identifier is updated, nothing new is created
		out = importer.import_csv("Rental Unit", f"barcode,id:rfid\nBC-{self.tag}-1,RF-NEW-{self.tag}\n")
		self.assertEqual(out["updated"], [unit.name])
		self.assertEqual(
			frappe.get_doc("Rental Unit", unit.name).external_ids[0].id_value, f"RF-NEW-{self.tag}"
		)

	def test_bad_row_is_reported_others_import(self):
		csv = (
			"customer_name,customer_type\n"
			f"Imp Cust 1 {self.tag},Individual\n"
			f"Imp Cust 2 {self.tag},NotAType\n"
			f"Imp Cust 3 {self.tag},Company\n"
		)
		out = importer.import_csv("Customer", csv)
		self.assertEqual(len(out["created"]), 2)
		self.assertEqual([e["row"] for e in out["errors"]], [3])
		self.assertTrue(frappe.db.exists("Customer", {"customer_name": f"Imp Cust 3 {self.tag}"}))

	def test_dry_run_saves_nothing(self):
		name = f"Imp Dry {self.tag}"
		out = importer.import_csv("Customer", f"customer_name\n{name}\n", dry_run=True)
		self.assertEqual(len(out["created"]), 1)
		self.assertFalse(frappe.db.exists("Customer", {"customer_name": name}))

	def test_unknown_columns_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			importer.import_csv("Customer", "customer_name,credit_limit\nX,1\n")
		with self.assertRaises(frappe.ValidationError):
			importer.import_csv("Rental Booking", "customer\nX\n")

	def test_api_permission(self):
		frappe.set_user(make_user("Rental Accountant"))
		with self.assertRaises(frappe.PermissionError):
			api.import_csv("Rental Item", self.items_csv())

	def test_template_and_new_presets(self):
		self.assertIn("id:rfid", importer.template("Rental Unit"))
		rental_type.install_presets()
		for name in ("Boat Charter", "Bicycle", "Meeting Room", "Tool", "Tour Guide"):
			self.assertTrue(frappe.db.exists("Rental Type", name), name)
		self.assertEqual(frappe.db.get_value("Rental Type", "Bicycle", "identification_mode"), "Pooled")
