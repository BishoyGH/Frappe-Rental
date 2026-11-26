import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api import booking as api
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services.setup import create_defaults
from frappe_rental.tests.test_lifecycle import make_type
from frappe_rental.tests.test_staff_app import make_user
from frappe_rental.tests.utils import make_customer


class TestBookingViews(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = ensure_setup_complete()
		create_defaults()
		currency = frappe.db.get_value("Company", company, "default_currency")
		if not frappe.db.exists("Rental Rate Card", "T18 Card"):
			frappe.get_doc(
				{
					"doctype": "Rental Rate Card",
					"card_name": "T18 Card",
					"currency": currency,
					"rates": [{"time_unit": "Day", "rate": 100}],
				}
			).insert()
		cls.rtype = make_type("T18 Type", requires_hold=0)
		cls.customer = make_customer()
		cls.item = (
			frappe.get_doc(
				{
					"doctype": "Rental Item",
					"item_name": f"T18 Kit {random_string(4)}",
					"rental_type": cls.rtype,
					"rate_card": "T18 Card",
				}
			)
			.insert()
			.name
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def unit(self):
		return (
			frappe.get_doc(
				{"doctype": "Rental Unit", "unit_name": f"T18 {random_string(6)}", "rental_item": self.item}
			)
			.insert()
			.name
		)

	def create(self, start="2026-07-01 10:00", end="2026-07-03 10:00", hold=0):
		return api.create(
			{
				"customer": self.customer,
				"rental_type": self.rtype,
				"from_datetime": start,
				"to_datetime": end,
				"lines": [{"rental_item": self.item, "rental_unit": self.unit()}],
			},
			hold=hold,
		)["name"]

	def test_create_and_detail(self):
		name = self.create()
		detail = api.get_detail(name)
		self.assertEqual(detail["status"], "Draft")
		self.assertEqual(detail["lines"][0]["rental_item"], self.item)
		self.assertTrue(detail["lines"][0]["item_name"].startswith("T18 Kit"))
		self.assertEqual(detail["grand_total"], 200)
		self.assertIn("confirm", detail["actions"])
		self.assertEqual(detail["activity"][-1]["text"], "Booking created")

	def test_create_with_hold_and_activity(self):
		name = self.create(start="2026-07-10 10:00", end="2026-07-11 10:00", hold=1)
		detail = api.get_detail(name)
		self.assertEqual(detail["status"], "Hold")
		self.assertIn("cancel", detail["actions"])
		self.assertIn("cancel", detail["actions"])
		doc = frappe.get_doc("Rental Booking", name)
		doc.status = "Draft"
		doc.save(ignore_version=False)
		doc.add_comment("Comment", "<p>Called the customer</p>")
		texts = [e["text"] for e in api.get_detail(name)["activity"]]
		self.assertIn("Status set to Draft", texts)
		self.assertIn("Called the customer", texts)
		api.confirm(name)
		detail = api.get_detail(name)
		self.assertEqual(detail["status"], "Confirmed")
		self.assertIn("invoice", detail["actions"])

	def test_create_requires_lines(self):
		with self.assertRaises(frappe.ValidationError):
			api.create({"customer": self.customer, "rental_type": self.rtype, "lines": []})

	def test_list_filters_sort_and_groups(self):
		a = self.create(start="2026-08-01 10:00", end="2026-08-02 10:00")
		b = self.create(start="2026-08-05 10:00", end="2026-08-06 10:00", hold=1)
		out = api.get_list(
			filters={"rental_type": self.rtype, "from_date": "2026-08-01", "to_date": "2026-08-31"},
			order_by="from_datetime",
			order="asc",
			group_by="status",
		)
		names = [r.name for r in out["rows"]]
		self.assertEqual(names[:2], [a, b])
		self.assertEqual(out["total"], len(names))
		self.assertTrue(out["rows"][0].item.startswith("T18 Kit"))
		groups = {g["value"]: g["count"] for g in out["groups"]}
		self.assertGreaterEqual(groups.get("Hold", 0), 1)
		held = api.get_list(filters=frappe.as_json({"status": "Hold", "search": b}))
		self.assertEqual([r.name for r in held["rows"]], [b])

	def test_list_rejects_unknown_inputs(self):
		with self.assertRaises(frappe.ValidationError):
			api.get_list(filters={"owner": "x"})
		with self.assertRaises(frappe.ValidationError):
			api.get_list(order_by="name; drop table")
		with self.assertRaises(frappe.ValidationError):
			api.get_list(group_by="owner")
		with self.assertRaises(frappe.ValidationError):
			api.get_list(filters={"status": "Bogus"})

	def test_options(self):
		opts = api.list_options()
		self.assertIn("Hold", opts["statuses"])
		self.assertIn(self.rtype, opts["rental_types"])

	def test_permissions(self):
		name = self.create(start="2026-09-01 10:00", end="2026-09-02 10:00")
		frappe.set_user(make_user())
		with self.assertRaises(frappe.PermissionError):
			api.get_list()
		with self.assertRaises(frappe.PermissionError):
			api.get_detail(name)
		with self.assertRaises(frappe.PermissionError):
			api.create({"lines": [{"rental_item": self.item}]})
		frappe.set_user("Administrator")
		frappe.set_user(make_user("Rental Accountant"))
		self.assertIn(name, [r.name for r in api.get_list(page_length=500)["rows"]])
		detail = api.get_detail(name)
		self.assertEqual(detail["actions"], [])
		with self.assertRaises(frappe.PermissionError):
			api.create({"lines": [{"rental_item": self.item}]})

	def test_search_link(self):
		rows = api.search_link("Rental Item", "T18 Kit")
		self.assertIn(self.item, [r["value"] for r in rows])
		unit = self.unit()
		self.assertIn(unit, [r["value"] for r in api.search_link("Rental Unit", "", rental_item=self.item)])
		with self.assertRaises(frappe.ValidationError):
			api.search_link("User", "")
