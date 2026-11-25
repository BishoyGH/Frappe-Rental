import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import rental_item as svc
from frappe_rental.services.setup import create_defaults


def make_type(name="T07 Camera", **kw):
	if not frappe.db.exists("Rental Type", name):
		frappe.get_doc(
			{"doctype": "Rental Type", "type_name": name, "mode": "Resource", "time_unit": "Day", **kw}
		).insert()
	return name


def make_rental_item(item_name="T07 Canon R5", **kw):
	return frappe.get_doc(
		{"doctype": "Rental Item", "item_name": item_name, "rental_type": make_type(), **kw}
	).insert()


class TestRentalItem(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = ensure_setup_complete()
		create_defaults()

	def test_save_creates_non_stock_item_with_income_account(self):
		doc = make_rental_item(description="Full-frame body")
		item = frappe.get_doc("Item", doc.item_code)
		self.assertEqual(item.item_name, "T07 Canon R5")
		self.assertEqual(item.is_stock_item, 0)
		self.assertEqual(item.description, "Full-frame body")
		if frappe.db.exists("Item Group", "Rentals"):
			self.assertEqual(item.item_group, "Rentals")
		expected = frappe.db.get_single_value("Rental Settings", "rental_income_account")
		company = frappe.db.get_single_value("Rental Settings", "default_company")
		if expected:
			row = next(r for r in item.item_defaults if r.company == company)
			self.assertEqual(row.income_account, expected)

	def test_resave_updates_same_item(self):
		doc = make_rental_item()
		count = frappe.db.count("Item")
		doc.item_name = "T07 Canon R5 Mk II"
		doc.save()
		doc.save()
		self.assertEqual(frappe.db.count("Item"), count)
		self.assertEqual(frappe.db.get_value("Item", doc.item_code, "item_name"), "T07 Canon R5 Mk II")

	def test_type_income_account_overrides_settings(self):
		settings_acc = frappe.db.get_single_value("Rental Settings", "rental_income_account")
		other = frappe.db.get_value(
			"Account",
			{"company": self.company, "root_type": "Income", "is_group": 0, "name": ["!=", settings_acc]},
			"name",
		)
		if not other:
			self.skipTest("needs a second income account")
		make_type("T07 Override", income_account=other)
		self.assertEqual(svc.income_account("T07 Override"), other)
		self.assertEqual(svc.income_account(make_type()), settings_acc)

	def test_item_edit_syncs_back(self):
		doc = make_rental_item()
		item = frappe.get_doc("Item", doc.item_code)
		item.item_name = "Renamed in ERPNext"
		item.description = "Edited in ERPNext"
		item.save()
		doc.reload()
		self.assertEqual(doc.item_name, "Renamed in ERPNext")
		self.assertEqual(doc.description, "Edited in ERPNext")

	def test_unrelated_item_is_ignored(self):
		item = frappe.get_doc("Item", make_rental_item().item_code)
		item.flags[svc.SYNC_FLAG] = True
		svc.sync_from_item(item)  # flagged: no-op
		svc.sync_from_item(frappe._dict(name="NO-SUCH", flags=frappe._dict(), get=lambda f: None))

	def test_unpublish_hides_page(self):
		# Route resolution only: rendering needs built website assets, which test sites may lack.
		from frappe.website.page_renderers.document_page import DocumentPage

		doc = make_rental_item(is_published=1)
		self.assertTrue(doc.route.startswith("rentals/"))
		self.assertTrue(DocumentPage(doc.route).can_render())
		doc.is_published = 0
		doc.save()
		self.assertFalse(DocumentPage(doc.route).can_render())

	def test_type_custom_field_shows_in_form(self):
		frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": "T07 Boat",
				"mode": "Resource",
				"time_unit": "Day",
				"custom_fields": [
					{
						"applies_to": "Rental Item",
						"label": "Length",
						"fieldname": "t07_length_m",
						"fieldtype": "Float",
					}
				],
			}
		).insert()
		self.assertTrue(frappe.get_meta("Rental Item").has_field("t07_length_m"))
		doc = make_rental_item("T07 Sailboat", t07_length_m=9.5)
		self.assertEqual(frappe.db.get_value("Rental Item", doc.name, "t07_length_m"), 9.5)
