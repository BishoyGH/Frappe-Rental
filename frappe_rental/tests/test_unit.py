import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from frappe_rental.api.unit import lookup
from frappe_rental.compat.erpnext import ensure_setup_complete
from frappe_rental.services import unit as svc


def make_type(mode):
	name = f"T08 {mode}"
	if not frappe.db.exists("Rental Type", name):
		frappe.get_doc(
			{
				"doctype": "Rental Type",
				"type_name": name,
				"mode": "Resource",
				"time_unit": "Day",
				"identification_mode": mode,
			}
		).insert()
	return name


def make_item(mode):
	return (
		frappe.get_doc(
			{"doctype": "Rental Item", "item_name": f"T08 {mode} item", "rental_type": make_type(mode)}
		)
		.insert()
		.name
	)


def unit(mode, **kw):
	return frappe.get_doc(
		{"doctype": "Rental Unit", "unit_name": f"T08 {mode} unit", "rental_item": make_item(mode), **kw}
	)


def raw(doctype, name, **kw):
	"""Insert a bare record without ERPNext validation; only its name matters for these tests."""
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, "name": name, **kw}).db_insert()
	return name


class TestRentalUnit(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_setup_complete()

	def test_none_mode(self):
		doc = unit("None").insert()
		self.assertEqual(doc.identification_mode, "None")
		self.assertEqual(frappe.db.get_value("Rental Unit", doc.name, "barcode"), doc.name)
		with self.assertRaises(frappe.ValidationError):
			unit("None", serial_no=raw("Serial No", f"T08-SN-{random_string(5)}", serial_no="x")).insert()

	def test_asset_mode(self):
		with self.assertRaises(frappe.ValidationError):
			unit("Asset").insert()
		asset = raw("Asset", f"T08-AST-{random_string(5)}")
		unit("Asset", asset=asset).insert()
		with self.assertRaises(frappe.ValidationError):
			unit("Asset", asset=asset).insert()  # one Asset per unit

	def test_serial_mode(self):
		with self.assertRaises(frappe.ValidationError):
			unit("Serial").insert()
		sn = f"T08-SN-{random_string(5)}"
		raw("Serial No", sn, serial_no=sn)
		unit("Serial", serial_no=sn).insert()
		with self.assertRaises(frappe.ValidationError):
			unit("Serial", serial_no=sn).insert()

	def test_batch_mode(self):
		with self.assertRaises(frappe.ValidationError):
			unit("Batch").insert()
		batch = f"T08-B-{random_string(5)}"
		raw("Batch", batch, batch_id=batch)
		self.assertEqual(unit("Batch", batch_no=batch).insert().identification_mode, "Batch")

	def test_pooled_mode(self):
		with self.assertRaises(frappe.ValidationError):
			unit("Pooled").insert()
		self.assertEqual(unit("Pooled", quantity_available=20).insert().quantity_available, 20)
		with self.assertRaises(frappe.ValidationError):
			unit("None", quantity_available=5).insert()

	def test_lookup_by_any_identifier(self):
		sn = f"T08-SN-{random_string(5)}"
		raw("Serial No", sn, serial_no=sn)
		imei = random_string(15)
		doc = unit("Serial", serial_no=sn, external_ids=[{"id_type": "IMEI", "id_value": imei}]).insert()
		for ident in (doc.name, sn, imei, frappe.db.get_value("Rental Unit", doc.name, "barcode")):
			self.assertEqual(lookup(ident)["name"], doc.name)
		self.assertIsNone(lookup("no-such-id"))
		with self.assertRaises(frappe.ValidationError):
			lookup("  ")

	def test_external_id_unique(self):
		plate = random_string(8)
		unit("None", external_ids=[{"id_type": "Plate", "id_value": plate}]).insert()
		with self.assertRaises(frappe.ValidationError):
			unit("None", external_ids=[{"id_type": "Plate", "id_value": plate}]).insert()

	def test_lookup_needs_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				lookup("anything")
		finally:
			frappe.set_user("Administrator")

	def test_parent_unit_tree(self):
		building = unit("None", is_group=1).insert()
		flat = unit("None", parent_rental_unit=building.name).insert()
		building.reload()
		flat.reload()
		self.assertTrue(building.lft < flat.lft < flat.rgt < building.rgt)

	def test_label_print_format(self):
		self.assertTrue(frappe.db.exists("Print Format", "Rental Unit Label"))
		doc = unit("None").insert()
		# Render the format's own template; the full print view needs built assets that test sites may lack.
		template = frappe.db.get_value("Print Format", "Rental Unit Label", "html")
		html = frappe.render_template(template, {"doc": frappe.get_doc("Rental Unit", doc.name)})
		self.assertIn(doc.name, html)
		self.assertIn("data:image/png;base64,", html)
		self.assertTrue(svc.qr_data_uri("x").startswith("data:image/png;base64,"))
