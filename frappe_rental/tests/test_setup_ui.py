import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import booking as booking_api
from frappe_rental.api import setup as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.test_staff_app import make_user


class TestSetupUI(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		currency = frappe.db.get_value("Company", company, "default_currency")
		if not frappe.db.exists("Rental Rate Card", "T20 Card"):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": "T20 Card",
					"currency": currency,
					"rates": [{"time_unit": "Hour", "rate": 40}],
				}
			).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_boat_example_end_to_end(self):
		tname = f"Boat {random_string(5)}"
		api.save_record(
			"Rental Type",
			{
				"type_name": tname,
				"mode": "Resource",
				"time_unit": "Hour",
				"identification_mode": "None",
				"min_duration": 2,
				"buffer_after": 45,
				"requires_hold": 1,
				"custom_fields": [
					{
						"applies_to": "Rental Item",
						"label": "Seats",
						"fieldname": "t20_seats",
						"fieldtype": "Int",
					},
					{
						"applies_to": "Rental Unit",
						"label": "Engine hours",
						"fieldname": "t20_engine_hours",
						"fieldtype": "Float",
					},
				],
			},
		)
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Rental Item", "fieldname": "t20_seats"}))
		self.assertEqual([f.fieldname for f in api.type_fields("Rental Item", tname)], ["t20_seats"])

		item = api.save_record(
			"Rental Item",
			{
				"item_name": f"Speedboat {random_string(4)}",
				"rental_type": tname,
				"rate_card": "T20 Card",
				"custom": {"t20_seats": 8},
			},
		)["name"]
		rec = api.get_record("Rental Item", item)
		self.assertEqual(rec["custom"]["t20_seats"], 8)
		self.assertEqual(rec["custom_meta"][0]["label"], "Seats")

		unit = api.save_record(
			"Rental Unit",
			{
				"unit_name": f"Boat 1 {random_string(4)}",
				"rental_item": item,
				"custom": {"t20_engine_hours": 120.5},
			},
		)["name"]
		self.assertEqual(frappe.db.get_value("Rental Unit", unit, "t20_engine_hours"), 120.5)
		self.assertEqual([u.name for u in api.get_record("Rental Item", item)["units"]], [unit])

		customer = api.save_record("Customer", {"customer_name": f"Sailor {random_string(4)}"})["name"]
		b = booking_api.create(
			{
				"customer": customer,
				"rental_type": tname,
				"from_datetime": "2027-08-01 10:00",
				"to_datetime": "2027-08-01 14:00",
				"lines": [{"rental_item": item, "rental_unit": unit}],
			},
			hold=1,
		)
		self.assertEqual(b["status"], "Hold")
		self.assertEqual(frappe.db.get_value("Rental Booking", b["name"], "grand_total"), 160)

		api.save_record("Rental Item", {"is_published": 1}, name=item)
		self.assertEqual(frappe.db.get_value("Rental Item", item, "is_published"), 1)
		listing = api.get_records("Rental Item", search=rec["item_name"])
		self.assertEqual([r.name for r in listing["rows"]], [item])
		units = api.get_records("Rental Unit", filters={"rental_item": item})
		self.assertEqual(units["total"], 1)

	def test_rejects_unknown_fields_and_doctypes(self):
		with self.assertRaises(frappe.ValidationError):
			api.save_record("Rental Item", {"item_name": "x", "owner": "evil@example.com"})
		with self.assertRaises(frappe.ValidationError):
			api.save_record("Rental Item", {"item_name": "x", "custom": {"not_a_field": 1}})
		with self.assertRaises(frappe.ValidationError):
			api.get_records("User")
		with self.assertRaises(frappe.ValidationError):
			api.get_records("Rental Unit", filters={"owner": "x"})

	def test_options(self):
		opts = api.form_options()
		self.assertIn("Hour", opts["time_units"])
		self.assertIn("Int", opts["field_types"])

	def test_permissions(self):
		frappe.set_user(make_user("Rental Accountant"))
		self.assertIn("rows", api.get_records("Rental Item"))
		with self.assertRaises(frappe.PermissionError):
			api.save_record("Rental Item", {"item_name": "Nope"})
		frappe.set_user("Administrator")
		frappe.set_user(make_user())
		with self.assertRaises(frappe.PermissionError):
			api.get_records("Rental Type")
